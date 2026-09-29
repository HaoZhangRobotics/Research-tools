# Marco Hutter 2023–2026 bibliographic catalog

`MarcoHutter_2023_2026_metadata.csv` contains the 253 Scholar records with titles, authors, year, venue, DOI and source links. Availability columns indicate whether the local corpus has an abstract, an Introduction extraction, or a PDF.

| Year | Records | Abstracts | Introductions | PDFs |
|---:|---:|---:|---:|---:|
| 2023 | 45 | 5 | 3 | 6 |
| 2024 | 67 | 16 | 10 | 16 |
| 2025 | 72 | 70 | 39 | 55 |
| 2026 | 69 | 69 | 58 | 61 |

The full abstracts, extracted introductions, and downloaded PDFs remain in the local ignored `output/` directory. Rebuild this metadata-only catalog after running the Scholar crawler with:

```bash
python tools/build_metadata_catalog.py
```
