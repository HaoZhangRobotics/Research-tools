"""Build repository-safe bibliographic catalogs from local crawler outputs.

Generated catalogs contain bibliographic metadata and source links only. They
intentionally omit abstracts, introductions, and downloaded full-text files.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def rss_catalog() -> int:
    source = ROOT / "tools/conference_crawler/output/rss_2023_2026_title_abstract_index.csv"
    if not source.exists():
        raise FileNotFoundError(f"Missing crawler output: {source}")
    with source.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    fields = ["year", "title", "authors", "doi", "source_url", "pdf_url", "pdf_status"]
    write_csv(ROOT / "tools/conference_crawler/catalog/rss_2023_2026_metadata.csv", fields, rows)
    return len(rows)


def hutter_catalog() -> int:
    source = ROOT / "tools/paper_crawler/output/MarcoHutter_2023_2026/papers.json"
    if not source.exists():
        raise FileNotFoundError(f"Missing crawler output: {source}")
    papers = json.loads(source.read_text(encoding="utf-8"))["papers"]
    fields = ["year", "title", "authors", "venue", "citations", "doi", "source_url",
              "pdf_url", "abstract_available", "introduction_available", "pdf_available"]
    rows = []
    for paper in papers:
        rows.append({
            **paper,
            "abstract_available": bool(paper.get("abstract")),
            "introduction_available": bool(paper.get("introduction")),
            "pdf_available": bool(paper.get("pdf_file")),
        })
    write_csv(ROOT / "tools/paper_crawler/catalog/MarcoHutter_2023_2026_metadata.csv", fields, rows)
    return len(rows)


def main() -> None:
    counts = rss_catalog(), hutter_catalog()
    print(f"Generated metadata catalogs: RSS={counts[0]}, Marco Hutter={counts[1]}")


if __name__ == "__main__":
    main()
