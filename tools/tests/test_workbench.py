from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest

ENTRYPOINT = Path(__file__).resolve().parents[1] / "app.py"


class WorkbenchTests(unittest.TestCase):
    def test_pages_load_and_crawler_modules_do_not_collide(self):
        app = AppTest.from_file(str(ENTRYPOINT)).run()
        self.assertFalse(app.exception)
        pages = [
            ("paper_crawler/app.py", "📚 科研论文采集器"),
            ("conference_crawler/app.py", "📑 会议论文采集器"),
            ("paper_crawler/app.py", "📚 科研论文采集器"),
            ("video_publisher/app.py", "🎬 科研视频发布"),
            ("home.py", "🧪 Research Tools"),
        ]
        for path, title in pages:
            with self.subTest(page=path):
                app.switch_page(path).run()
                self.assertFalse(app.exception)
                self.assertEqual(app.title[0].value, title)


if __name__ == "__main__":
    unittest.main()
