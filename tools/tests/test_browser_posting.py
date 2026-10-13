"""Exercise browser posting against synthetic local pages, never real accounts."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from video_publisher.browser_worker import post_with_browser, PostingError

PAGE = '''<html><head><meta charset="utf-8"></head><body>
<input type="file" accept="video/mp4" data-testid="fileInput" onchange="document.getElementById('done').hidden=false;document.getElementById('attachments').hidden=false">
<div id="done" hidden>上传完成</div><div id="attachments" data-testid="attachments" hidden>video attached</div>
<input placeholder="填写标题"><textarea placeholder="填写简介"></textarea>
<div contenteditable="true" data-testid="tweetTextarea_0"></div>
<button data-testid="tweetButton" onclick="document.getElementById('receipt').textContent='SUCCESS'">发布</button>
<div id="receipt"></div></body></html>'''


class BrowserPostingTests(unittest.TestCase):
    def test_three_platform_flows_on_isolated_fixture_pages(self):
        with tempfile.TemporaryDirectory() as directory, sync_playwright() as playwright:
            video = Path(directory) / "fixture.mp4"
            video.write_bytes(b"fixture video - no real upload")
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            try:
                for platform in ["哔哩哔哩", "小红书", "X"]:
                    with self.subTest(platform=platform):
                        page = browser.new_page()
                        html = PAGE.replace("SUCCESS", "Your post was sent" if platform == "X" else "发布成功")
                        page.route("**/*", lambda route: route.fulfill(content_type="text/html", body=html))
                        post = {"title": "Research video", "description": "Description", "tags": ["robotics"]}
                        result = post_with_browser(page, platform, str(video), post, confirmation_timeout=2, upload_timeout=5000)
                        self.assertEqual(result["state"], "submitted")
                        if platform != "X":
                            self.assertEqual(page.get_by_placeholder("填写标题").input_value(), "Research video")
                            self.assertIn("#robotics", page.get_by_placeholder("填写简介").input_value())
                        page.close()
            finally:
                browser.close()

    def test_click_without_receipt_is_unknown(self):
        with tempfile.TemporaryDirectory() as directory, sync_playwright() as playwright:
            video = Path(directory) / "fixture.mp4"
            video.write_bytes(b"fixture")
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            try:
                page = browser.new_page()
                page.route("**/*", lambda route: route.fulfill(content_type="text/html", body=PAGE.replace("SUCCESS", "")))
                result = post_with_browser(page, "X", str(video), {"title": "Test", "description": "", "tags": []}, confirmation_timeout=0.1)
                self.assertEqual(result["state"], "unknown")
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
