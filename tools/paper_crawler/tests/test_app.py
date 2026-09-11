from pathlib import Path
import shutil
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from streamlit.testing.v1 import AppTest
from crawler import Blocked, Paper

APP = Path(__file__).resolve().parents[1] / 'app.py'


class AppTests(unittest.TestCase):
    def launch(self):
        app = AppTest.from_file(str(APP)).run()
        self.assertFalse(app.exception)
        app.text_input[0].set_value('https://scholar.google.com/citations?user=abc123XYZ')
        app.button[0].click().run()
        self.assertFalse(app.exception)
        return app

    def test_collect_filter_export_without_pdf(self):
        app = self.launch()
        app.checkbox[1].uncheck()
        app.number_input[0].set_value(2024)
        app.number_input[1].set_value(2024)
        app.text_input[1].set_value('robot')
        app.checkbox[2].uncheck()
        papers = [Paper('a:1', 'Robot learning', 2024), Paper('a:2', 'Biology', 2024), Paper('a:3', 'Robot old', 2020)]
        with patch('crawler.ScholarClient.publications', return_value=iter(papers)), patch('crawler.ScholarClient.detail'):
            app.button[1].click().run(timeout=10)
        self.assertFalse(app.exception)
        selected, directory, meta = app.session_state['result']
        try:
            self.assertEqual([p.id for p in selected], ['a:1'])
            self.assertEqual(meta['state'], '完成')
            self.assertTrue((directory / 'papers.csv').exists())
        finally:
            shutil.rmtree(directory)

    def test_block_keeps_partial_source(self):
        app = self.launch()
        def interrupted(self, author_id):
            yield Paper('a:1', 'Saved paper', 2024)
            raise Blocked('验证码')
        with patch('crawler.ScholarClient.publications', interrupted):
            app.button[1].click().run(timeout=10)
        self.assertFalse(app.exception)
        selected, directory, meta = app.session_state['result']
        try:
            self.assertIn('中断', meta['state'])
            self.assertIn('Saved paper', (directory / 'source' / 'papers.json').read_text())
            self.assertFalse(meta['list_complete'])
        finally:
            shutil.rmtree(directory)
