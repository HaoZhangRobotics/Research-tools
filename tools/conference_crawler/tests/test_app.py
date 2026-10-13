from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from streamlit.testing.v1 import AppTest
from conference_crawler.crawler import Client, DEFAULT_URL

APP = Path(__file__).resolve().parents[1] / 'app.py'
INDEX = '<div class="content"><a href="p001.html">Test paper</a></div>'
DETAIL = '<meta name="citation_title" content="Test paper"><meta name="citation_author" content="A">'


class AppTests(unittest.TestCase):
    def test_collect_metadata_and_export(self):
        with tempfile.TemporaryDirectory() as d:
            app = AppTest.from_file(str(APP)).run()
            self.assertFalse(app.exception)
            app.checkbox[0].uncheck()
            app.text_input[2].set_value(d)
            with patch.object(Client, 'html', side_effect=[(INDEX, DEFAULT_URL), (DETAIL, DEFAULT_URL)]):
                app.button[0].click().run(timeout=10)
            self.assertFalse(app.exception)
            directory, report = app.session_state['conference_result']
            self.assertEqual(report['state'], '完成')
            self.assertEqual(len(report['papers']), 1)
            self.assertEqual(len(app.dataframe[0].value), 1)
            self.assertTrue((directory / 'papers.csv').exists())

    def test_invalid_input_is_visible(self):
        app = AppTest.from_file(str(APP)).run()
        app.text_input[0].set_value('file:///etc/passwd')
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.error)


if __name__ == '__main__': unittest.main()
