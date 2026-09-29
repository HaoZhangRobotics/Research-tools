import importlib.util
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("conference_crawler", Path(__file__).parents[1] / "crawler.py")
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
URL = c.DEFAULT_URL
INDEX = '''<h1>RSS XXII</h1><div class="content"><table><tr><td>
<a href="p001.html">Paper 一</a><i>A, B</i></td><td><a href="p001.pdf">PDF</a></td></tr>
<tr><td><a href="p001.html#top">duplicate</a></td></tr></table>
<a href="../rss21/p001.html">Other year</a><a href="authors.html">Authors</a></div>'''
DETAIL = '''<meta name="citation_title" content="Paper 一"><meta name="citation_author" content="A">
<meta name="citation_author" content="B"><meta name="citation_publication_date" content="2026/07/13">
<meta name="citation_pdf_url" content="http://www.roboticsproceedings.org/rss22/p001.pdf">
<p><b>Abstract:</b></p><p>Full abstract.</p><pre>@INPROCEEDINGS{x, DOI = {10.1/test}}</pre>'''
PDF = b'%PDF-1.7\nexample\n%%EOF\n'


class Response:
    def __init__(self, body=PDF):
        self.body = body
        self.headers = {"Content-Length": str(len(body))}
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def iter_content(self, _): yield self.body


class Tests(unittest.TestCase):
    def paper(self): return c.parse_index(INDEX, URL)[0]

    def test_index_scope_and_dedup(self):
        papers = c.parse_index(INDEX, URL)
        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]["authors"], "A, B")
        self.assertTrue(papers[0]["pdf_url"].endswith('/rss22/p001.pdf'))

    def test_detail_metadata(self):
        p = self.paper()
        c.parse_detail(DETAIL, p["source_url"], p)
        self.assertEqual(p["abstract"], "Full abstract.")
        self.assertEqual(p["authors"], "A; B")
        self.assertEqual(p["year"], "2026")
        self.assertEqual(p["doi"], "10.1/test")
        self.assertTrue(p["pdf_url"].startswith("https://"))

    def test_generic_selector(self):
        with self.assertRaises(ValueError): c.parse_index(INDEX, "https://example.org/")
        with self.assertRaises(ValueError): c.parse_index(INDEX, "https://example.org/", "a[")
        p = c.parse_index('<a class="paper" href="a.pdf">A</a>', "https://example.org/", "a.paper")[0]
        self.assertEqual(p["detail_status"], "direct_pdf")

    def test_pdf_validation_size_and_resume(self):
        with tempfile.TemporaryDirectory() as d:
            directory, p, client = Path(d), self.paper(), c.Client()
            with patch.object(client, "get", return_value=Response()) as get:
                c.download_pdf(client, p, directory)
                self.assertTrue(c.valid_pdf(directory / p["pdf_file"]))
                c.download_pdf(client, p, directory)
                self.assertEqual(get.call_count, 1)
            (directory / p["pdf_file"]).unlink()
            for body, limit in [(b'<html>not PDF</html>', 100), (PDF, 5), (b'%PDF-1.7 truncated', 100)]:
                with patch.object(client, "get", return_value=Response(body)):
                    with self.assertRaises(ValueError): c.download_pdf(client, p, directory, limit)
                self.assertEqual(list(directory.rglob('*.part')), [])

    def test_end_to_end_resume_and_export(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(c.Client, "html", side_effect=[(INDEX, URL), (DETAIL, URL)]), patch.object(c.Client, "get", return_value=Response()):
                directory, report = c.crawl(URL, d, progress=lambda _: None)
            self.assertEqual(report["state"], "完成")
            self.assertTrue((directory / 'papers.bib').read_text().startswith('@INPROCEEDINGS'))
            with patch.object(c.Client, "html", return_value=(INDEX, URL)) as html, patch.object(c.Client, "get") as get:
                _, report = c.crawl(URL, d, progress=lambda _: None)
            self.assertEqual(html.call_count, 1)
            get.assert_not_called()
            self.assertEqual(report["papers"][0]["pdf_status"], "downloaded")

    def test_parallel_download_bound_and_checkpoint(self):
        papers = [dict(self.paper(), id=str(i)) for i in range(8)]
        active, peak = 0, 0
        lock = threading.Lock()
        def download(client, paper, directory):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.01)
            paper['pdf_status'] = 'downloaded'
            with lock:
                active -= 1
        with patch.object(c, 'download_pdf', side_effect=download):
            c.download_all(papers, Path('.'), c.Client(), 2, lambda: None, lambda _: None)
        self.assertEqual(peak, 2)
        self.assertTrue(all(p['pdf_status'] == 'downloaded' for p in papers))

    def test_download_block_stops_scheduling(self):
        papers = [dict(self.paper(), id=str(i)) for i in range(8)]
        with patch.object(c, 'download_pdf', side_effect=c.Blocked('429')) as download:
            with self.assertRaises(c.Blocked):
                c.download_all(papers, Path('.'), c.Client(), 2, lambda: None, lambda _: None)
        self.assertLessEqual(download.call_count, 2)

    def test_blocked_preserves_full_list(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(c.Client, "html", side_effect=[(INDEX, URL), c.Blocked('429')]):
                _, report = c.crawl(URL, d, progress=lambda _: None)
            self.assertTrue(report["list_complete"])
            self.assertEqual(len(report["papers"]), 1)
            self.assertIn('中断', report["state"])


if __name__ == '__main__': unittest.main()
