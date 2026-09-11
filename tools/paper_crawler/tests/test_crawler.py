import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bs4 import BeautifulSoup
from crawler import (Blocked, CrawlError, Paper, ScholarClient, download_pdf,
                     export_results, matches, scholar_id)


def response(data, url="https://example.org/paper"):
    result = Mock()
    result.__enter__ = Mock(return_value=result)
    result.__exit__ = Mock(return_value=False)
    result.iter_content.side_effect = lambda size: iter([data])
    result.url = url
    return result


class CrawlerTests(unittest.TestCase):
    def test_author_id(self):
        self.assertEqual(scholar_id("https://scholar.google.com/citations?hl=en&user=abc123XYZ"), "abc123XYZ")
        with self.assertRaises(ValueError):
            scholar_id("https://example.com/no-user")

    def test_filter_boundaries_unknown_year_and_keywords(self):
        p = Paper("1", "Robot Learning", 2024, abstract="Manipulation")
        self.assertTrue(matches(p, 2024, 2024, ["unrelated", "MANIPULATION"]))
        self.assertFalse(matches(p, 2025))
        self.assertFalse(matches(p, keywords=["biology"]))
        p.year = None
        self.assertFalse(matches(p, 2020))
        self.assertTrue(matches(p))

    def test_pagination_deduplicates(self):
        def html(ids, more):
            rows = ''.join(f'<tr class="gsc_a_tr"><td><a class="gsc_a_at" href="/citations?citation_for_view=a:{i}">Paper {i}</a><div class="gs_gray">Authors</div><div class="gs_gray">Venue</div></td><td class="gsc_a_y">2024</td></tr>' for i in ids)
            return BeautifulSoup(f'<table id="gsc_a_t">{rows}</table><button id="gsc_bpf_more" {more}></button>', 'html.parser')
        client = ScholarClient()
        client.page = Mock(side_effect=[html([1, 2], ""), html([2, 3], "disabled")])
        self.assertEqual([p.id for p in client.publications("abc123XYZ")], ["a:1", "a:2", "a:3"])
        self.assertEqual(client.page.call_args_list[1].args[1]["cstart"], 100)

    def test_unrecognized_list_is_not_empty_success(self):
        client = ScholarClient()
        client.page = Mock(return_value=BeautifulSoup('<html>Sign in</html>', 'html.parser'))
        with self.assertRaises(CrawlError):
            list(client.publications("abc123XYZ"))

    def test_block_stops_without_retry(self):
        client = ScholarClient()
        client.session.get = Mock(return_value=Mock(status_code=429, text=""))
        with self.assertRaises(Blocked):
            client.page("https://scholar.google.com")
        client.session.get.assert_called_once()

    def test_detail_metadata(self):
        client = ScholarClient()
        client.page = Mock(return_value=BeautifulSoup('''
          <a id="gsc_oci_title" href="https://arxiv.org/abs/2401.00001">Full title</a>
          <div class="gs_scl"><div class="gsc_oci_field">Authors</div><div class="gsc_oci_value">A, B</div></div>
          <div class="gs_scl"><div class="gsc_oci_field">Publication date</div><div class="gsc_oci_value">2024/1/1</div></div>
          <div class="gs_scl"><div class="gsc_oci_field">Description</div><div class="gsc_oci_value">Robot control</div></div>
          <div class="gsc_oci_title_ggi"><a href="https://arxiv.org/pdf/2401.00001">PDF</a></div>
        ''', 'html.parser'))
        p = Paper('1', 'Truncated…', None)
        client.detail(p)
        self.assertEqual((p.title, p.year, p.authors), ('Full title', 2024, 'A, B'))
        self.assertEqual(p.abstract, 'Robot control')
        self.assertEqual(p.pdf_url, 'https://arxiv.org/pdf/2401.00001')

    def test_pdf_metadata_download_and_export(self):
        p = Paper("author:1", "A / paper", 2024, source_url="https://example.org/article")
        session = Mock()
        session.get.side_effect = [response(b'<meta name="citation_pdf_url" content="/paper.pdf">'), response(b'%PDF-1.7\nexample')]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            download_pdf(p, root / "pdfs", session)
            self.assertEqual(p.status, "已下载")
            self.assertTrue(Path(p.pdf_file).read_bytes().startswith(b'%PDF-'))
            export_results([p], root, {"state": "完成"})
            report = json.loads((root / 'papers.json').read_text())
            self.assertTrue((root / report['papers'][0]['pdf_file']).exists())
            self.assertIn('## PDF 文件', (root / 'README.md').read_text())
            self.assertIn('论文信息汇总', (root / 'index.html').read_text())
            self.assertIn('打开 PDF', (root / 'index.html').read_text())
            download_pdf(p, root / "pdfs", session)
            self.assertEqual(session.get.call_count, 2)

    def test_html_is_not_pdf(self):
        p = Paper("1", "Paper", None, pdf_url="https://example.org/fake.pdf")
        session = Mock()
        session.get.return_value = response(b'<html>Login required</html>')
        with tempfile.TemporaryDirectory() as tmp:
            download_pdf(p, Path(tmp), session)
            self.assertEqual(p.status, "未获取")
            self.assertEqual(list(Path(tmp).glob('*.pdf')), [])

    def test_size_limit_cleans_partial(self):
        p = Paper("1", "Paper", 2024, pdf_url="https://example.org/p.pdf")
        session = Mock()
        r = response(b'')
        r.iter_content.side_effect = lambda size: iter([b'%PDF-1.7', b'x' * 40])
        session.get.return_value = r
        with tempfile.TemporaryDirectory() as tmp:
            download_pdf(p, Path(tmp), session, max_bytes=20)
            self.assertEqual(p.status, "未获取")
            self.assertEqual(list(Path(tmp).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
