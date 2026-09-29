"""Enrich a saved author corpus from already-recorded public PDF/source links.

This deliberately does not retry Google Scholar. It downloads only links already
present in the corpus and records the result, extracted abstract, and intro text.
"""
from __future__ import annotations

import json
import os
import re
import csv
from html import escape
from urllib.parse import quote
import sys
import time
from pathlib import Path

from crawler import Paper, download_pdf

CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def clean(value):
    return CONTROL_CHARS.sub("", value) if isinstance(value, str) else value


def introduction(pdf_path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        reader = PdfReader(str(pdf_path), strict=False)
        text = "\n".join((page.extract_text() or "") for page in reader.pages[:12])
    except Exception:
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    # Find a standalone Introduction heading and stop at the next major section.
    start = None
    for i, line in enumerate(lines):
        if line.lower().strip(" .:0123456789") in {"introduction", "1 introduction", "i introduction"}:
            start = i + 1
            break
        if line.lower() in {"introduction", "1. introduction", "1 introduction", "i. introduction"}:
            start = i + 1
            break
    if start is None:
        # Some PDFs place the heading and first paragraph on the same extracted line.
        for i, line in enumerate(lines):
            low = line.lower()
            for marker in ("1 introduction", "1. introduction", "i. introduction"):
                pos = low.find(marker)
                if pos >= 0:
                    tail = line[pos + len(marker):].strip(" .:")
                    lines[i] = tail
                    start = i
                    break
            if start is not None:
                break
    if start is None:
        return ""
    stop = len(lines)
    for i in range(start, len(lines)):
        low = lines[i].lower().strip(" .:0123456789")
        if low in {"related work", "background", "preliminaries", "problem formulation", "method", "methodology", "approach"}:
            stop = i
            break
    body = " ".join(lines[start:stop])
    return " ".join(body.split())[:12000]


def abstract_from_pdf(pdf_path: Path) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(pdf_path), strict=False)
        text = "\n".join((page.extract_text() or "") for page in reader.pages[:3])
    except Exception:
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for i, line in enumerate(lines):
        match = re.search(r"\babstract\b\s*[:.]?\s*(.*)", line, re.I)
        if not match:
            continue
        chunks = [match.group(1)] if match.group(1) else []
        for nxt in lines[i + 1:]:
            if re.match(r"^(keywords?|index terms|1\.?\s*introduction|introduction)\b", nxt, re.I):
                break
            chunks.append(nxt)
        result = " ".join(" ".join(chunks).split())
        if len(result) > 80:
            return result[:6000]
    return ""


def main(folder: str, export_only: bool = False) -> None:
    root = Path(folder)
    data_path = root / "papers.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    papers = data["papers"]
    pdf_dir = root / "pdfs"
    done = 0
    for row in papers:
        existing_pdf = Path(row["pdf_file"]) if row.get("pdf_file") else None
        if existing_pdf and not existing_pdf.is_absolute() and not existing_pdf.exists():
            existing_pdf = root / existing_pdf
        if existing_pdf and existing_pdf.exists():
            if not row.get("abstract"):
                row["abstract"] = abstract_from_pdf(existing_pdf)
                if row["abstract"]:
                    row["abstract_status"] = "已从公开 PDF 首页抽取"
            if not row.get("introduction"):
                row["introduction"] = introduction(existing_pdf)
                if row["introduction"]:
                    row["intro_status"] = "已从公开 PDF 抽取"
            continue
        if export_only:
            continue
        if not row.get("pdf_url") and not row.get("source_url"):
            arxiv = re.search(r"arxiv\s*(?:e-prints?|preprint)?[, :]*\s*(?:arxiv:)?\s*(\d{4}\.\d{4,5})", row.get("venue", ""), re.I)
            if arxiv:
                row["pdf_url"] = f"https://arxiv.org/pdf/{arxiv.group(1)}"
        if not row.get("pdf_url") and not row.get("source_url"):
            row["status"] = "无已记录的公开 PDF 链接"
            continue
        paper = Paper(**{k: row.get(k, "") for k in Paper.__dataclass_fields__})
        download_pdf(paper, pdf_dir)
        row.update({"pdf_url": paper.pdf_url, "pdf_file": paper.pdf_file,
                    "status": paper.status, "error": paper.error})
        if paper.pdf_file:
            intro = introduction(Path(paper.pdf_file))
            row["introduction"] = intro
            if not row.get("abstract"):
                row["abstract"] = abstract_from_pdf(Path(paper.pdf_file))
                if row["abstract"]:
                    row["abstract_status"] = "已从公开 PDF 首页抽取"
            if intro:
                row["intro_status"] = "已从公开 PDF 抽取"
            else:
                row["intro_status"] = "PDF 已下载，但未识别 Introduction 标题"
        else:
            row["intro_status"] = "未下载到公开 PDF"
        done += 1
        if done % 10 == 0:
            data["papers"] = papers
            data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"checkpoint: attempted {done}; pdfs {sum(bool(x.get('pdf_file')) for x in papers)}; intros {sum(bool(x.get('introduction')) for x in papers)}", flush=True)
        time.sleep(1.0)
    data["papers"] = papers
    data["downloaded"] = sum(bool(x.get("pdf_file")) for x in papers)
    data["abstract_count"] = sum(bool(x.get("abstract")) for x in papers)
    data["introduction_count"] = sum(bool(x.get("introduction")) for x in papers)
    data["state"] = "Scholar 列表已完整；详情部分受验证码限制；已补抓记录中的公开 PDF 链接。"
    for row in papers:
        for key, value in row.items():
            row[key] = clean(value)
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    # Keep a readable title/abstract/introduction index, with provenance and honest gaps.
    parts = ["# Marco Hutter 论文标题、摘要与 Introduction（2023–2026）", "",
             f"记录 {len(papers)} 篇；摘要 {data['abstract_count']} 篇；PDF {data['downloaded']} 份；Introduction {data['introduction_count']} 篇。",
             "Scholar 详情抓取曾遇验证码；缺失字段保持标注，不作推测。", ""]
    for p in papers:
        pdf_ref = p.get("pdf_file") or p.get("pdf_url") or p.get("status", "未获取")
        if p.get("pdf_file"):
            pdf_ref = quote(Path(os.path.relpath(Path(p["pdf_file"]).resolve(), root.resolve())).as_posix())
        parts += [f"## {p.get('year') or '年份未知'} · {p.get('title','')}", "",
                  f"作者：{p.get('authors','')}", f"发表渠道：{p.get('venue','')}",
                  f"来源：{p.get('source_url') or p.get('scholar_url') or ''}",
                  f"PDF：[{pdf_ref}]({pdf_ref})" if p.get("pdf_file") else f"PDF：{pdf_ref}", "",
                  "### Abstract", "", p.get("abstract") or "未获取摘要。", "",
                  "### Introduction", "", p.get("introduction") or p.get("intro_status", "未获取 Introduction 正文。"), ""]
    (root / "titles_and_introductions.md").write_text("\n".join(parts), encoding="utf-8")
    csv_path = root / "papers.csv"
    fields = list(dict.fromkeys([*papers[0].keys(), "abstract_status", "introduction", "intro_status"]))
    with csv_path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(papers)
    yearly = {}
    for p in papers:
        bucket = yearly.setdefault(p.get("year"), {"papers": 0, "abstracts": 0, "intros": 0, "pdfs": 0})
        bucket["papers"] += 1
        bucket["abstracts"] += bool(p.get("abstract"))
        bucket["intros"] += bool(p.get("introduction"))
        bucket["pdfs"] += bool(p.get("pdf_file"))
    readme = ["# Marco Hutter · 2023–2026 论文汇总", "",
              f"共 {len(papers)} 篇；摘要 {data['abstract_count']} 篇；PDF {data['downloaded']} 份；Introduction {data['introduction_count']} 篇。",
              "Scholar 作者页列表已完整；详情页受验证码限制。摘要和 Introduction 仅在成功取得公开记录/PDF 时收录，空缺处保留状态说明。", "",
              "- [标题、摘要与 Introduction 索引](titles_and_introductions.md)",
              "- [CSV 表格](papers.csv)", "- [JSON 数据](papers.json)", "", "| 年份 | 论文 | 摘要 | Introduction | PDF |", "|---:|---:|---:|---:|---:|"]
    for year, counts in sorted(yearly.items()):
        readme.append(f"| {year} | {counts['papers']} | {counts['abstracts']} | {counts['intros']} | {counts['pdfs']} |")
    (root / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")
    html_rows = []
    for i, p in enumerate(papers, 1):
        title = escape(str(p.get("title", "")))
        abstract = escape(str(p.get("abstract", "")))
        intro = escape(str(p.get("introduction", "")))
        html_rows.append(f"<tr><td>{i}</td><td>{escape(str(p.get('year') or ''))}</td><td>{title}</td><td>{'有' if abstract else '缺'}</td><td>{'有' if intro else '缺'}</td></tr>")
    page = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Marco Hutter 论文索引</title>
<style>body{{font:15px/1.6 system-ui,sans-serif;max-width:1200px;margin:32px auto;padding:0 18px;color:#182536}}table{{border-collapse:collapse;width:100%}}th,td{{padding:8px;border-bottom:1px solid #ddd;text-align:left}}th{{position:sticky;top:0;background:#edf2f7}}td:nth-child(3){{min-width:400px}}</style>
<h1>Marco Hutter · 2023–2026</h1><p>{len(papers)} 篇论文 · 摘要 {data['abstract_count']} 篇 · PDF {data['downloaded']} 份 · Introduction {data['introduction_count']} 篇</p>
<p><a href="titles_and_introductions.md">完整摘要和 Introduction</a> · <a href="papers.csv">CSV</a> · <a href="papers.json">JSON</a></p>
<table><thead><tr><th>#</th><th>年份</th><th>标题</th><th>摘要</th><th>Introduction</th></tr></thead><tbody>{''.join(html_rows)}</tbody></table></html>'''
    (root / "index.html").write_text(page, encoding="utf-8")
    print(f"complete: records={len(papers)}, abstracts={data['abstract_count']}, pdfs={data['downloaded']}, intros={data['introduction_count']}")


if __name__ == "__main__":
    main(sys.argv[1], "--export-only" in sys.argv[2:])
