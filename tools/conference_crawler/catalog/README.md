# RSS 2023–2026 bibliographic catalog

`rss_2023_2026_metadata.csv` contains 619 records: title, authors, year, DOI, source and PDF links, and local acquisition status.

| Year | Records |
|---:|---:|
| 2023 | 112 |
| 2024 | 134 |
| 2025 | 163 |
| 2026 | 210 |

The full abstract index and downloaded PDFs remain in the local ignored `output/` directory. Rebuild this metadata-only catalog after running the conference crawler with:

```bash
python tools/build_metadata_catalog.py
```
