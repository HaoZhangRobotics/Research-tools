import json
import fcntl
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from video_publisher import publish_queue
from video_publisher.browser_worker import publish_receipt
from streamlit.testing.v1 import AppTest


class QueueTests(unittest.TestCase):
    def test_only_checked_platforms_run_and_results_are_not_duplicated(self):
        calls = []
        def publish(platform, *args):
            calls.append(platform)
            if platform == "小红书":
                raise ValueError("Not logged in")
            return {"state": "submitted", "message": "test receipt"}
        post = {"platforms": ["哔哩哔哩", "小红书"]}
        with tempfile.TemporaryDirectory() as directory, patch.object(publish_queue, "ROOT", Path(directory)):
            result = publish_queue.publish_selected(post, "video.mp4", "a" * 32, publisher=publish)
            self.assertEqual(calls, ["哔哩哔哩", "小红书"])
            self.assertEqual(result["小红书"]["state"], "failed")
            publish_queue.publish_selected(post, "video.mp4", "a" * 32, publisher=publish)
            self.assertEqual(calls, ["哔哩哔哩", "小红书", "小红书"])

    def test_unknown_or_interrupted_attempt_is_not_retried(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(publish_queue, "ROOT", Path(directory)):
            def interrupted(*args):
                raise ConnectionError("Response lost")
            result = publish_queue.publish_selected({"platforms": ["X"]}, "video.mp4", "b" * 32, publisher=interrupted)
            self.assertEqual(result["X"]["state"], "unknown")
            with patch.object(publish_queue, "publish_one") as publish:
                publish_queue.publish_selected({"platforms": ["X"]}, "video.mp4", "b" * 32)
                publish.assert_not_called()

    def test_upload_response_cannot_be_mistaken_for_post_receipt(self):
        self.assertIsNone(publish_receipt("哔哩哔哩", "https://member.bilibili.com/upload", {"code": 0}))
        receipt = publish_receipt("哔哩哔哩", "https://member.bilibili.com/x/vu/web/add/v3", {"code": 0, "data": {"bvid": "BVtest"}})
        self.assertEqual(receipt["url"], "https://www.bilibili.com/video/BVtest")
        self.assertIsNone(publish_receipt("哔哩哔哩", "https://wrong.example/x/vu/web/add", {"code": 0, "data": {"bvid": "BVtest"}}))

    def test_same_job_cannot_run_concurrently(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(publish_queue, "ROOT", Path(directory)):
            jobs = Path(directory) / "output" / "publish_jobs"
            jobs.mkdir(parents=True)
            with (jobs / ("c" * 32 + ".lock")).open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaises(ValueError), patch.object(publish_queue, "publish_one") as publish:
                    publish_queue.publish_selected({"platforms": ["X"]}, "test.mp4", "c" * 32)
                publish.assert_not_called()

    def test_unchecking_platform_disables_old_draft_publish(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
        app.switch_page("video_publisher/app.py").run()
        app.session_state["video_post"] = {
            "title": "Title", "description": "Body", "video_filename": "video.mp4",
            "video_size_bytes": 3, "platforms": ["YouTube"], "tags": [], "youtube_privacy": "private",
        }
        next(x for x in app.checkbox if x.label == "YouTube").check().run()
        next(x for x in app.checkbox if x.label.startswith("我已检查预览")).check().run()
        self.assertFalse(next(x for x in app.button if x.label == "发布到勾选的平台").disabled)
        next(x for x in app.checkbox if x.label == "YouTube").uncheck().run()
        self.assertTrue(next(x for x in app.button if x.label == "发布到勾选的平台").disabled)
        self.assertFalse(app.exception)

    def test_five_platform_checkboxes_visible_and_unselected(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
        app.switch_page("video_publisher/app.py").run()
        self.assertFalse(app.exception)
        labels = ["抖音", "B站（哔哩哔哩）", "小红书", "X", "YouTube"]
        for label in labels:
            checkbox = next(x for x in app.checkbox if x.label == label)
            self.assertFalse(checkbox.value)


if __name__ == "__main__":
    unittest.main()
