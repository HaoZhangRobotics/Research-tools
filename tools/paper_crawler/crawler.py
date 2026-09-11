"""Google Scholar author collection and bounded public PDF downloads."""
from __future__ import annotations

import csv
import hashlib
from html import escape
import io
import json
import os
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://scholar.google.com"


class CrawlError(RuntimeError):
    pass


class Blocked(CrawlError):
    pass


def scholar_id(value: str) -> str:
    value = value.strip()
    if "://" in value:
        value = parse_qs(urlparse(value).query).get("user", [""])[0]
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,32}", value):
        raise ValueError("请输入有效的 Scholar 作者 ID 或包含 user= 的主页地址。")
    return value


def txt(node) -> str:
    return node.get_text(" ", strip=True) if node else ""


@dataclass
class Paper:
    id: str
    title: str
    year: int | None
    authors: str = ""
    venue: str = ""
    citations: int = 0
    scholar_url: str = ""
    abstract: str = ""
    source_url: str = ""
    pdf_url: str = ""
    pdf_file: str = ""
    status: str = "待下载"
    error: str = ""


def matches(paper: Paper, start=None, end=None, keywords=()) -> bool:
    if start is not None or end is not None:
        if paper.year is None:
            return False
        if start is not None and paper.year < start:
            return False
        if end is not None and paper.year > end:
            return False
    haystack = f"{paper.title} {paper.abstract} {paper.venue}".casefold()
    return not keywords or any(k.casefold() in haystack for k in keywords)


class ScholarClient:
    def __init__(self, delay=2.0):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "ResearchTools/0.1 (personal scholarly research)"
        self.delay = max(1.0, delay)
        self.last_request = 0.0

    def page(self, url, params=None):
        time.sleep(max(0, self.delay - (time.monotonic() - self.last_request)))
        self.last_request = time.monotonic()
        try:
            response = self.session.get(url, params=params, timeout=(10, 30))
        except requests.RequestException as exc:
            raise CrawlError(f"Scholar 网络请求失败：{exc}") from exc
        if response.status_code in (403, 429) or any(
            marker in response.text.lower()
            for marker in ("unusual traffic", "g-recaptcha", "gs_captcha_ccl", "not a robot")
        ):
            raise Blocked("Google Scholar 限流或要求验证码。已停止，请稍后重试或在浏览器检查访问状态。")
        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            raise CrawlError(f"Scholar 请求失败：{exc}") from exc
        return BeautifulSoup(response.text, "html.parser")

    def search_authors(self, name):
        soup = self.page(BASE + "/citations", {"view_op": "search_authors", "mauthors": name, "hl": "en"})
        authors = []
        for node in soup.select(".gsc_1usr"):
            link = node.select_one(".gs_ai_name a")
            if not link:
                continue
            authors.append({"id": scholar_id(urljoin(BASE, link["href"])), "name": txt(link),
                            "affiliation": txt(node.select_one(".gs_ai_aff")),
                            "interests": txt(node.select_one(".gs_ai_int"))})
        if not authors and not soup.select_one("#gsc_sa_ccl"):
            raise CrawlError("无法识别作者搜索页面，可能需要登录或页面结构已变化。可尝试输入作者主页。")
        return authors

    def publications(self, author_id):
        seen = set()
        offset = 0
        while True:
            soup = self.page(BASE + "/citations", {"user": scholar_id(author_id), "hl": "en",
                             "cstart": offset, "pagesize": 100, "sortby": "pubdate"})
            if not soup.select_one("#gsc_a_t"):
                raise CrawlError("无法识别论文列表，请检查作者 ID 或 Scholar 访问状态。")
            rows = soup.select(".gsc_a_tr")
            added = 0
            for row in rows:
                link = row.select_one(".gsc_a_at")
                if not link:
                    continue
                url = urljoin(BASE, link["href"])
                pid = parse_qs(urlparse(url).query).get("citation_for_view", [url])[0]
                if pid in seen:
                    continue
                seen.add(pid)
                added += 1
                year = txt(row.select_one(".gsc_a_y"))
                gray = row.select(".gs_gray")
                citations = re.sub(r"\D", "", txt(row.select_one(".gsc_a_ac")))
                yield Paper(pid, txt(link), int(year) if year.isdigit() else None,
                            txt(gray[0]) if gray else "", txt(gray[1]) if len(gray) > 1 else "",
                            int(citations or 0), url)
            more = soup.select_one("#gsc_bpf_more")
            if more is not None and more.has_attr("disabled"):
                break
            if not rows:
                break
            if added == 0:
                raise CrawlError("Scholar 返回重复分页，已停止；当前列表可能不完整。")
            if more is None:
                raise CrawlError("无法确认分页是否结束；当前列表可能不完整。")
            offset += 100

    def detail(self, paper):
        soup = self.page(paper.scholar_url)
        if not soup.select_one("#gsc_oci_title"):
            raise CrawlError("无法识别论文详情页面。")
        paper.title = txt(soup.select_one("#gsc_oci_title")) or paper.title
        fields = {txt(row.select_one(".gsc_oci_field")): txt(row.select_one(".gsc_oci_value"))
                  for row in soup.select(".gs_scl")}
        paper.authors = fields.get("Authors", paper.authors)
        paper.abstract = fields.get("Description", "")
        paper.venue = fields.get("Journal", fields.get("Conference", paper.venue))
        year = re.match(r"\d{4}", fields.get("Publication date", ""))
        if year:
            paper.year = int(year[0])
        title_link = soup.select_one("a#gsc_oci_title, #gsc_oci_title a")
        paper.source_url = urljoin(BASE, title_link["href"]) if title_link else ""
        pdf_link = soup.select_one(".gsc_oci_title_ggi a")
        paper.pdf_url = urljoin(BASE, pdf_link["href"]) if pdf_link else ""


def pdf_candidates(url: str) -> list[str]:
    parsed = urlparse(url)
    if parsed.hostname in ("arxiv.org", "www.arxiv.org", "export.arxiv.org") and parsed.path.startswith("/abs/"):
        return ["https://arxiv.org/pdf/" + parsed.path[5:], url]
    return [url] if url else []


def download_pdf(paper: Paper, directory: Path, session=None, max_bytes=80 * 1024 * 1024):
    """Try Scholar full text and publisher metadata; never save HTML as a PDF."""
    session = session or requests.Session()
    directory.mkdir(parents=True, exist_ok=True)
    suffix = hashlib.sha256(paper.id.encode()).hexdigest()[:12]
    title = re.sub(r"[^\w\- .]", "_", paper.title)[:50].strip(" .") or "paper"
    target = directory / f"{paper.year or 'unknown'}_{title}_{suffix}.pdf"
    if target.exists():
        with target.open("rb") as existing:
            if existing.read(5) == b"%PDF-":
                paper.pdf_file, paper.status, paper.error = str(target), "已下载", ""
                return
    queue = list(dict.fromkeys(pdf_candidates(paper.pdf_url) + pdf_candidates(paper.source_url)))
    seen, errors = set(), []
    partial = target.with_suffix(".part")
    while queue and len(seen) < 6:
        url = queue.pop(0)
        if url in seen or urlparse(url).scheme not in ("https", "http"):
            continue
        seen.add(url)
        try:
            with session.get(url, timeout=(10, 45), stream=True) as response:
                response.raise_for_status()
                chunks = response.iter_content(64 * 1024)
                head = next((chunk for chunk in chunks if chunk), b"")
                if head.startswith(b"%PDF-"):
                    size = len(head)
                    if size > max_bytes:
                        raise ValueError("PDF 超过大小限制")
                    with partial.open("wb") as out:
                        out.write(head)
                        for chunk in chunks:
                            size += len(chunk)
                            if size > max_bytes:
                                raise ValueError(f"PDF 超过 {max_bytes / (1024 * 1024):g} MB 大小限制")
                            out.write(chunk)
                    partial.replace(target)
                    paper.pdf_file, paper.pdf_url, paper.status, paper.error = str(target), response.url, "已下载", ""
                    return
                # Inspect only a bounded HTML prefix for publishers' standard PDF metadata.
                html = bytearray(head)
                for chunk in chunks:
                    if len(html) >= 1024 * 1024:
                        break
                    html.extend(chunk)
                soup = BeautifulSoup(bytes(html), "html.parser")
                for meta in soup.select('meta[name="citation_pdf_url"], meta[name="wkhealth_pdf_url"]'):
                    if meta.get("content"):
                        queue.extend(pdf_candidates(urljoin(response.url, meta["content"])))
                errors.append("链接未返回 PDF")
        except (requests.RequestException, OSError, ValueError) as exc:
            errors.append(str(exc))
        finally:
            partial.unlink(missing_ok=True)
    paper.status = "未获取"
    paper.error = "; ".join(dict.fromkeys(errors)) or "未找到公开 PDF 链接"


def export_results(papers: list[Paper], directory: Path, metadata: dict):
    directory.mkdir(parents=True, exist_ok=True)
    rows = [asdict(p) for p in papers]
    # File references stay usable after the complete directory is moved or unzipped.
    for row in rows:
        if row["pdf_file"]:
            row["pdf_file"] = Path(os.path.relpath(row["pdf_file"], directory)).as_posix()
    report = {**metadata, "count": len(rows), "downloaded": sum(p.status == "已下载" for p in papers), "papers": rows}
    payloads = {"papers.json": json.dumps(report, ensure_ascii=False, indent=2)}
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(Paper.__dataclass_fields__))
    writer.writeheader()
    writer.writerows(rows)
    payloads["papers.csv"] = stream.getvalue()
    lines = ["# 论文信息汇总", "", f"采集状态：{metadata.get('state', '')}", "",
             f"论文记录：{len(rows)}；已获取 PDF 的记录：{report['downloaded']}", ""]
    for label, key in (("数据来源", "source"), ("下载范围", "download_scope")):
        if metadata.get(key):
            lines += [f"{label}：{metadata[key]}", ""]
    lines += ["| 年份 | 论文 | 作者 | 发表渠道 | 引用 | PDF 状态 |", "|---|---|---|---|---:|---|"]
    def cell(value):
        return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")
    for p in papers:
        lines.append("| " + " | ".join(map(cell, [p.year, p.title, p.authors, p.venue, p.citations, p.status])) + " |")
    lines += ["", "## PDF 文件", ""]
    for row in rows:
        if row["pdf_file"]:
            from urllib.parse import quote
            lines.append(f"- [{cell(row['title'])}]({quote(row['pdf_file'])})")
        else:
            lines.append(f"- {cell(row['title'])}：{cell(row['error'] or row['status'])}")
    payloads["README.md"] = "\n".join(lines) + "\n"
    payloads["index.html"] = html_report(rows, metadata)
    for name, value in payloads.items():
        path = directory / name
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(value, encoding="utf-8-sig" if name.endswith("csv") else "utf-8")
        temp.replace(path)


def html_report(rows: list[dict], metadata: dict) -> str:
    from urllib.parse import quote
    def safe(value):
        return escape(str(value if value is not None else ""), quote=True)
    table, downloads = [], []
    seen_pdf_files = set()
    for index, row in enumerate(rows, 1):
        title = safe(row['title'])
        if urlparse(row['scholar_url']).scheme in ('http', 'https'):
            title = f'<a href="{safe(row["scholar_url"])}">{title}</a>'
        table.append('<tr>' + ''.join(f'<td>{value}</td>' for value in
                     (index, safe(row['year']), title, safe(row['authors']), safe(row['venue']),
                      safe(row['citations']), safe(row['status']), safe(row['error']))) + '</tr>')
        if row['pdf_file'] and row['pdf_file'] not in seen_pdf_files:
            seen_pdf_files.add(row['pdf_file'])
            downloads.append(f'<article><h3>{index}. {safe(row["title"])}</h3>'
                             f'<p>{safe(row["abstract"])}</p>'
                             f'<a class="download" href="{safe(quote(row["pdf_file"]))}">打开 PDF</a></article>')
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>论文采集结果</title>
<style>body{font:16px/1.65 system-ui,sans-serif;background:#f3f6fa;color:#15243c;margin:0}
main{max-width:1440px;margin:auto;padding:32px}header,article,.list{background:white;border:1px solid #dce4ee;border-radius:12px;padding:24px;margin:20px 0}
h1,h2,h3{line-height:1.3}header{border-top:5px solid #247d89}.list{overflow:auto;max-height:65vh;padding:0}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;padding:12px;border-bottom:1px solid #e6edf4;vertical-align:top}
th{position:sticky;top:0;background:#e8eff6}td:nth-child(3){min-width:260px}a{color:#096a83}article p{color:#526174}.download{display:inline-block;padding:8px 18px;background:#e5f3f4;border-radius:6px}
</style><main><header><h1>''' + safe(metadata.get('author', {}).get('name', '')) + ''' · 论文采集结果</h1><p>''' + safe(metadata.get('state', '')) + '''</p><p>''' + f'{len(rows)} 条记录 · {len(downloads)} 份 PDF' + '''</p><p>''' + safe(metadata.get('download_scope', '')) + '''</p><p><a href="papers.csv">下载 CSV</a> · <a href="papers.json">下载 JSON</a> · <a href="#pdfs">跳到 PDF 文件</a></p></header>
<h2>论文信息汇总</h2><div class="list"><table><thead><tr><th>#</th><th>年份</th><th>论文</th><th>作者</th><th>发表渠道</th><th>引用</th><th>PDF 状态</th><th>备注</th></tr></thead><tbody>''' + ''.join(table) + '''</tbody></table></div>
<h2 id="pdfs">已下载的论文 PDF</h2>''' + (''.join(downloads) or '<p>尚无已下载的 PDF，请查看上方状态。</p>') + '</main></html>'
