"""Supplement a saved Marco Hutter corpus from Crossref and Semantic Scholar."""
from __future__ import annotations

import difflib
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from crawler import Paper, download_pdf
from enrich_author_corpus import abstract_from_pdf, introduction


def norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split())


def score(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def crossref_match(session, paper):
    url = "https://api.crossref.org/works"
    response = session.get(url, params={"query.title": paper["title"], "rows": 6}, timeout=25)
    response.raise_for_status()
    items = response.json().get("message", {}).get("items", [])
    best = None
    for item in items:
        titles = item.get("title") or []
        if not titles:
            continue
        similarity = score(paper["title"], titles[0])
        issued = item.get("issued", {}).get("date-parts", [[None]])[0][0]
        if similarity < 0.89 or (issued and paper.get("year") and abs(int(issued) - int(paper["year"])) > 1):
            continue
        author_names = [f"{a.get('given','')} {a.get('family','')}".strip().lower() for a in item.get("author", [])]
        # Crossref often omits consortium contributors; only reject an explicit author list
        # that is complete enough to contradict the Scholar record.
        scholar_names = (paper.get("authors") or "").lower()
        if author_names and len(author_names) >= 2 and "marco hutter" in scholar_names:
            if not any("marco" in name and "hutter" in name for name in author_names) and similarity < 0.98:
                continue
        if best is None or similarity > best[0]:
            best = (similarity, item)
    return best


def semantic_match(session, paper):
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    response = session.get(url, params={"query": paper["title"], "limit": 5,
                          "fields": "title,year,abstract,openAccessPdf,authors,externalIds,url"}, timeout=25)
    if response.status_code == 429:
        time.sleep(5)
        return None
    response.raise_for_status()
    items = response.json().get("data", [])
    best = None
    for item in items:
        similarity = score(paper["title"], item.get("title", ""))
        year = item.get("year")
        if similarity < 0.91 or (year and paper.get("year") and abs(int(year) - int(paper["year"])) > 1):
            continue
        author_names = [a.get("name", "").lower() for a in item.get("authors", [])]
        if author_names and not any("marco" in name and "hutter" in name for name in author_names) and similarity < 0.98:
            continue
        if best is None or similarity > best[0]:
            best = (similarity, item)
    return best


def main(folder: str):
    root = Path(folder)
    data_path = root / "papers.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    papers = data["papers"]
    session = requests.Session()
    session.headers["User-Agent"] = "ResearchTools/1.0 (academic metadata enrichment; public API use)"
    targets = [p for p in papers if p.get("year") in (2025, 2026) and (not p.get("abstract") or not p.get("introduction"))]
    tried = 0
    for paper in targets:
        changed = False
        cr = None
        if not paper.get("abstract") or not paper.get("doi"):
            try:
                cr = crossref_match(session, paper)
            except (requests.RequestException, ValueError, KeyError) as exc:
                paper["crossref_status"] = f"查询失败：{exc}"
            if cr:
                similarity, item = cr
                paper["doi"] = paper.get("doi") or item.get("DOI", "")
                paper["crossref_title_match"] = round(similarity, 3)
                if not paper.get("abstract") and item.get("abstract"):
                    text = BeautifulSoup(item["abstract"], "html.parser").get_text(" ", strip=True)
                    if len(text) > 80:
                        paper["abstract"] = text
                        paper["abstract_status"] = "Crossref 摘要（题名匹配）"
                        changed = True
                if not paper.get("source_url") and item.get("URL"):
                    paper["source_url"] = item["URL"]
                    changed = True
                for link in item.get("link", []):
                    if "pdf" in (link.get("content-type", "") + link.get("URL", "")).lower():
                        paper["pdf_url"] = paper.get("pdf_url") or link.get("URL", "")
                        break
        pdf_path = Path(paper["pdf_file"]) if paper.get("pdf_file") else None
        if pdf_path and not pdf_path.exists():
            pdf_path = root / pdf_path
        if not paper.get("introduction") and not (pdf_path and pdf_path.exists()):
            try:
                ss = semantic_match(session, paper)
                if ss:
                    similarity, item = ss
                    oa = item.get("openAccessPdf") or {}
                    if item.get("abstract") and not paper.get("abstract"):
                        paper["abstract"] = item["abstract"]
                        paper["abstract_status"] = "Semantic Scholar 摘要（题名及作者匹配）"
                        changed = True
                    if oa.get("url"):
                        paper["pdf_url"] = oa["url"]
                        paper["semantic_scholar_id"] = item.get("paperId", "")
                        paper["semantic_title_match"] = round(similarity, 3)
                        changed = True
            except (requests.RequestException, ValueError, KeyError) as exc:
                paper["semantic_scholar_status"] = f"查询失败：{exc}"
            if paper.get("pdf_url") and not (pdf_path and pdf_path.exists()):
                target = Paper(**{k: paper.get(k, "") for k in Paper.__dataclass_fields__})
                download_pdf(target, root / "pdfs", session=session)
                paper.update({"pdf_url": target.pdf_url, "pdf_file": target.pdf_file,
                              "status": target.status, "error": target.error})
                if target.pdf_file:
                    pdf_path = Path(target.pdf_file)
                    intro = introduction(pdf_path)
                    if intro:
                        paper["introduction"] = intro
                        paper["intro_status"] = "已从新增公开 PDF 抽取"
                        changed = True
                    if not paper.get("abstract"):
                        abstract = abstract_from_pdf(pdf_path)
                        if abstract:
                            paper["abstract"] = abstract
                            paper["abstract_status"] = "已从新增公开 PDF 首页抽取"
                            changed = True
        tried += 1
        if tried % 5 == 0:
            data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"checked {tried}/{len(targets)}; 2025–26 abstracts {sum(bool(x.get('abstract')) for x in papers if x.get('year') in (2025, 2026))}; intros {sum(bool(x.get('introduction')) for x in papers if x.get('year') in (2025, 2026))}", flush=True)
        time.sleep(0.8)
    data["abstract_count"] = sum(bool(x.get("abstract")) for x in papers)
    data["downloaded"] = sum(bool(x.get("pdf_file")) for x in papers)
    data["introduction_count"] = sum(bool(x.get("introduction")) for x in papers)
    data["papers"] = papers
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"complete: checked={tried}; 2025–26 abstracts={sum(bool(x.get('abstract')) for x in papers if x.get('year') in (2025, 2026))}; intros={sum(bool(x.get('introduction')) for x in papers if x.get('year') in (2025, 2026))}; PDFs={data['downloaded']}")


if __name__ == "__main__":
    main(sys.argv[1])
