"""Collect a proceedings index, paper metadata and publicly linked PDFs."""
from __future__ import annotations

import argparse
import csv
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import hashlib
from html import escape
import json
from pathlib import Path
import re
import subprocess
import time
import threading
from urllib.parse import urldefrag, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from soupsieve.util import SelectorSyntaxError

DEFAULT_URL = "https://www.roboticsproceedings.org/rss22/index.html"
OUTPUT = Path(__file__).resolve().parent / "output"


class Blocked(RuntimeError):
    pass


class CurlResponse:
    def __init__(self, body, url):
        self.body, self.url = body, url
        self.headers = {"Content-Length": str(len(body)), "Content-Type": "application/pdf"}
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def iter_content(self, chunk_size):
        for start in range(0, len(self.body), chunk_size):
            yield self.body[start:start + chunk_size]


def web_url(base, value):
    url = urldefrag(urljoin(base, value))[0]
    if urlparse(url).scheme not in ("http", "https") or not urlparse(url).hostname:
        raise ValueError(f"不是 HTTP(S) 地址：{url}")
    # RSS metadata still contains legacy HTTP URLs.
    if urlparse(base).scheme == "https" and urlparse(url).netloc == urlparse(base).netloc:
        url = re.sub(r"^http:", "https:", url)
    return url


def text(node):
    return node.get_text(" ", strip=True) if node else ""


def equivalent_url(left, right):
    """Treat the proceedings site's www and apex hosts as the same source."""
    a, b = urlparse(left), urlparse(right)
    ahost = a.hostname.removeprefix("www.") if a.hostname else ""
    bhost = b.hostname.removeprefix("www.") if b.hostname else ""
    return (a.scheme, ahost, a.path, a.query) == (b.scheme, bhost, b.path, b.query)


def parse_index(html, url, selector=None):
    soup = BeautifulSoup(html, "html.parser")
    rss = urlparse(url).hostname in ("www.roboticsproceedings.org", "roboticsproceedings.org")
    if not rss and not selector:
        raise ValueError("其他会议请指定论文链接 CSS 选择器（--selector），例如 a.paper-link。")
    try:
        links = soup.select(selector or '.content a[href]')
    except SelectorSyntaxError as exc:
        raise ValueError(f"CSS 选择器格式错误：{exc}") from exc
    papers, seen = [], set()
    for link in links:
        if not link.get("href"):
            continue
        target = web_url(url, link["href"])
        if rss and not selector and not (
            urlparse(target).netloc == urlparse(url).netloc
            and urlparse(target).path.rsplit("/", 1)[0] == urlparse(url).path.rsplit("/", 1)[0]
            and re.fullmatch(r"p\d+\.html", urlparse(target).path.rsplit("/", 1)[-1])
        ):
            continue
        if target in seen:
            continue
        seen.add(target)
        row = link.find_parent("tr")
        pdf = row.select_one('a[href$=".pdf"]') if row else None
        direct = urlparse(target).path.lower().endswith(".pdf")
        papers.append(dict(id=hashlib.sha256(target.encode()).hexdigest()[:16],
                           title=text(link) or Path(urlparse(target).path).stem,
                           authors=text(row.select_one("i")) if row else "", year="",
                           venue=text(soup.select_one("h1")), source_url=target,
                           pdf_url=target if direct else web_url(url, pdf["href"]) if pdf else "",
                           abstract="", doi="", bibtex="", pdf_file="",
                           detail_status="direct_pdf" if direct else "pending",
                           pdf_status="pending", detail_error="", pdf_error=""))
    if not papers:
        raise ValueError("未识别到论文链接，请检查目录地址或 CSS 选择器。")
    return papers


def parse_detail(html, url, paper):
    soup = BeautifulSoup(html, "html.parser")
    def meta(name):
        return [m.get("content", "") for m in soup.find_all("meta", attrs={"name": name})]
    for key, name in (("title", "citation_title"), ("venue", "citation_conference_title"),
                      ("doi", "citation_doi")):
        values = meta(name)
        if values:
            paper[key] = values[0]
    if meta("citation_author"):
        paper["authors"] = "; ".join(meta("citation_author"))
    date = (meta("citation_publication_date") or meta("citation_date") or [""])[0]
    year = re.search(r"\b\d{4}\b", date)
    paper["year"] = year[0] if year else paper["year"]
    pdfs = meta("citation_pdf_url")
    link = soup.select_one('a[href$=".pdf"]')
    if pdfs or link:
        paper["pdf_url"] = web_url(url, pdfs[0] if pdfs else link["href"])
    abstract = soup.select_one('#abstract, .abstract')
    label = soup.find(["b", "strong"], string=re.compile(r"^\s*Abstract\s*:?\s*$", re.I))
    if abstract:
        paper["abstract"] = text(abstract)
    elif label:
        parent = label.find_parent("p")
        paper["abstract"] = text(parent.find_next_sibling("p")) if parent else ""
    else:
        paper["abstract"] = (meta("citation_abstract") or [""])[0]
    bib = soup.find("pre", string=re.compile(r"@", re.S))
    paper["bibtex"] = text(bib)
    if not paper["doi"]:
        match = re.search(r"DOI\s*=\s*[{\"]([^}\"]+)", paper["bibtex"], re.I)
        paper["doi"] = match[1] if match else ""
    if not meta("citation_title") and not paper["pdf_url"] and not paper["bibtex"]:
        raise ValueError("详情页无可识别的论文元数据或 PDF，可能需要网站专用适配。")
    paper["detail_status"], paper["detail_error"] = "ok", ""


class RateLimiter:
    def __init__(self, delay):
        self.delay = max(0.2, delay)
        self.last_request = 0.0
        self.lock = threading.Lock()

    def wait(self):
        with self.lock:
            time.sleep(max(0, self.delay - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()


class Client:
    def __init__(self, delay=1.0, limiter=None):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131 Safari/537.36"
        self.limiter = limiter or RateLimiter(delay)

    def get(self, url, stream=False):
        for attempt in range(3):
            self.limiter.wait()
            response = None
            try:
                response = self.session.get(url, timeout=(15, 90), stream=stream)
                if response.status_code in (403, 429):
                    raise Blocked(f"网站返回 {response.status_code}，已停止；可稍后重新运行。")
                response.raise_for_status()
                if stream and response.headers.get("Content-Type", "").lower().startswith("text/html"):
                    response.close()
                    body = subprocess.run(["curl", "-L", "--max-time", "180", "-A", self.session.headers["User-Agent"], "-sS", url], check=True, capture_output=True).stdout
                    return CurlResponse(body, url)
                return response
            except Blocked:
                response.close()
                raise
            except requests.RequestException:
                if response is not None:
                    response.close()
                if attempt == 2 or (response is not None and response.status_code < 500):
                    raise
                time.sleep(2 ** attempt)

    def html(self, url):
        with self.get(url) as response:
            response.encoding = response.apparent_encoding
            html = response.text
            if "one moment, please" in html.lower() or "just a moment" in html.lower():
                try:
                    result = subprocess.run(["curl", "-L", "--max-time", "90", "-A", self.session.headers["User-Agent"], "-sS", url], check=True, capture_output=True)
                except subprocess.CalledProcessError as exc:
                    raise requests.RequestException(f"curl 获取页面失败：{exc}") from exc
                html = result.stdout.decode("utf-8", errors="replace")
            return html, response.url


def valid_pdf(path):
    if not path.is_file() or path.stat().st_size < 10:
        return False
    with path.open("rb") as handle:
        if handle.read(5) != b"%PDF-":
            return False
        handle.seek(max(0, path.stat().st_size - 2048))
        return b"%%EOF" in handle.read()


def download_pdf(client, paper, directory, max_bytes=200 * 1024 * 1024):
    target = directory / "pdfs" / f"{paper['id']}.pdf"
    target.parent.mkdir(parents=True, exist_ok=True)
    if valid_pdf(target):
        paper.update(pdf_file=str(target.relative_to(directory)), pdf_status="downloaded", pdf_error="")
        return
    paper["pdf_file"] = ""
    if not paper["pdf_url"]:
        paper.update(pdf_status="unavailable", pdf_error="详情页未提供 PDF 链接")
        return
    temp = target.with_suffix(".part")
    try:
        with client.get(paper["pdf_url"], stream=True) as response:
            expected = int(response.headers.get("Content-Length", 0))
            if expected > max_bytes:
                raise ValueError("PDF 超过大小上限")
            size = 0
            with temp.open("wb") as handle:
                for chunk in response.iter_content(128 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError("PDF 超过大小上限")
                    handle.write(chunk)
            if expected and not response.headers.get("Content-Encoding") and size != expected:
                raise ValueError("PDF 下载不完整")
        if not valid_pdf(temp):
            raise ValueError("响应不是完整 PDF（文件头或 EOF 校验失败）")
        temp.replace(target)
        paper.update(pdf_file=str(target.relative_to(directory)), pdf_status="downloaded", pdf_error="")
    finally:
        temp.unlink(missing_ok=True)


def save(directory, report):
    directory.mkdir(parents=True, exist_ok=True)
    temp = directory / "papers.json.tmp"
    temp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(directory / "papers.json")
    papers = report["papers"]
    if papers:
        with (directory / "papers.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(papers[0]))
            writer.writeheader()
            writer.writerows(papers)
    (directory / "papers.bib").write_text("\n\n".join(p["bibtex"] for p in papers if p["bibtex"]), encoding="utf-8")
    rows = []
    for i, p in enumerate(papers, 1):
        pdf = f'<a href="{escape(p["pdf_file"], quote=True)}">本地 PDF</a>' if p["pdf_file"] else escape(p["pdf_error"] or p["pdf_status"])
        rows.append(f'<tr><td>{i}</td><td><a href="{escape(p["source_url"], quote=True)}">{escape(p["title"])}</a><details><summary>摘要</summary>{escape(p["abstract"])}</details></td><td>{escape(p["authors"])}</td><td>{pdf}</td></tr>')
    (directory / "index.html").write_text('<!doctype html><html lang="zh"><meta charset="utf-8"><title>会议论文汇总</title><style>body{font:16px system-ui;margin:40px}table{border-collapse:collapse;width:100%}td,th{padding:12px;border:1px solid #ddd;text-align:left}details{margin-top:12px}a{color:#2563eb}</style><h1>会议论文汇总</h1><p>' + escape(report["state"]) + f' · {len(papers)} 篇</p><table><tr><th>#</th><th>论文</th><th>作者</th><th>PDF</th></tr>' + ''.join(rows) + '</table></html>', encoding="utf-8")


def download_all(papers, directory, client, workers, checkpoint, progress):
    """Bound in-flight work; workers own sessions and return results to the writer."""
    stopped = threading.Event()
    def task(paper):
        result = dict(paper)
        worker = Client(limiter=client.limiter)
        try:
            if not stopped.is_set():
                download_pdf(worker, result, directory)
        except Blocked:
            stopped.set()
            raise
        except (requests.RequestException, ValueError) as exc:
            result.update(pdf_status="failed", pdf_error=str(exc))
        finally:
            worker.session.close()
        return result

    pool = ThreadPoolExecutor(max_workers=workers)
    pending = {}
    indices = iter(range(len(papers)))
    failure = None
    completed = 0
    def submit_next():
        index = next(indices, None)
        if index is not None and not stopped.is_set():
            pending[pool.submit(task, papers[index])] = index
    try:
        for _ in range(workers):
            submit_next()
        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                index = pending.pop(future)
                try:
                    papers[index].update(future.result())
                except (Blocked, OSError) as exc:
                    stopped.set()
                    failure = exc
                completed += 1
                checkpoint()
                progress(f"PDF {completed}/{len(papers)} · {papers[index]['title']}")
            if not stopped.is_set():
                for _ in done:
                    submit_next()
    finally:
        stopped.set()
        pool.shutdown(wait=True, cancel_futures=True)
        for future, index in pending.items():
            if not future.cancelled() and future.exception() is None:
                papers[index].update(future.result())
        checkpoint()
    if failure:
        raise failure


def crawl(url=DEFAULT_URL, output=None, selector=None, fetch_pdf=True, delay=1.0, progress=print, workers=4):
    if not 1 <= workers <= 4:
        raise ValueError("并发数必须在 1–4 之间")
    url = web_url(url, url)
    directory = Path(output) if output else OUTPUT / (re.sub(r"[^\w.-]", "_", urlparse(url).netloc + urlparse(url).path) + '_' + hashlib.sha256(url.encode()).hexdigest()[:8])
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / "source"
    source.mkdir(exist_ok=True)
    report = dict(url=url, selector=selector, state="采集中", list_complete=False, papers=[])
    previous = {}
    if (directory / "papers.json").exists():
        old = json.loads((directory / "papers.json").read_text(encoding="utf-8"))
        reusable_empty = not old.get("papers") and not old.get("list_complete")
        if (not equivalent_url(old["url"], url) or old.get("selector") != selector) and not reusable_empty:
            raise ValueError("输出目录已有其他采集任务，请更换目录。")
        previous = {p["id"]: p for p in old["papers"]}
        report["papers"] = old["papers"]
    client = Client(delay)
    try:
        html, final_url = client.html(url)
        (source / "index.html").write_text(html, encoding="utf-8")
        papers = parse_index(html, final_url, selector)
        for p in papers:
            if p["id"] in previous:
                p.update(previous[p["id"]])
        report.update(papers=papers, list_complete=True)
        save(directory, report)
        progress(f"已发现 {len(papers)} 篇论文；输出：{directory}")
        for i, paper in enumerate(papers, 1):
            progress(f"详情 {i}/{len(papers)} · {paper['title']}")
            if paper["detail_status"] not in ("ok", "direct_pdf"):
                try:
                    html, detail_url = client.html(paper["source_url"])
                    (source / f"{paper['id']}.html").write_text(html, encoding="utf-8")
                    parse_detail(html, detail_url, paper)
                except Blocked:
                    raise
                except (requests.RequestException, ValueError) as exc:
                    paper.update(detail_status="failed", detail_error=str(exc))
                save(directory, report)
        if fetch_pdf:
            download_all(papers, directory, client, workers,
                         lambda: save(directory, report), progress)
        failed = sum(p["detail_status"] == "failed" or (fetch_pdf and p["pdf_status"] != "downloaded") for p in papers)
        report["state"] = f"完成（{failed} 篇存在失败或缺失）" if failed else "完成"
    except (Blocked, requests.RequestException, ValueError, OSError) as exc:
        report["state"] = f"中断：{exc}"
    except KeyboardInterrupt:
        report["state"] = "用户中断，可使用相同输出目录继续"
    finally:
        client.session.close()
        save(directory, report)
    progress(f"{report['state']}；共 {len(report['papers'])} 篇，PDF {sum(p['pdf_status'] == 'downloaded' for p in report['papers'])} 份")
    return directory, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", nargs="?", default=DEFAULT_URL)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--selector", help="其他会议目录中的论文链接 CSS 选择器")
    parser.add_argument("--no-pdf", action="store_true")
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    args = parser.parse_args()
    _, report = crawl(args.url, args.output, args.selector, not args.no_pdf, args.delay, workers=args.workers)
    return 0 if report["state"] == "完成" else 1


if __name__ == "__main__":
    raise SystemExit(main())
