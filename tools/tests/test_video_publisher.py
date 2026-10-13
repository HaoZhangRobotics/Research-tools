from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from google.oauth2.credentials import Credentials
from streamlit.testing.v1 import AppTest
from video_publisher import youtube
from video_publisher.media import video_path

ENTRYPOINT = Path(__file__).resolve().parents[1] / "app.py"


class VideoPublisherTests(unittest.TestCase):
    def launch(self):
        app = AppTest.from_file(str(ENTRYPOINT)).run()
        app.switch_page("video_publisher/app.py").run()
        self.assertFalse(app.exception)
        return app

    def test_preview_has_copyable_title_and_description(self):
        app = self.launch()
        app.session_state["video_post"] = {
            "title": "科研视频标题", "description": "可复制的科研视频文案",
            "video_filename": "test.mp4", "video_size_bytes": 3,
            "platforms": ["YouTube"], "tags": [], "youtube_privacy": "private",
        }
        app.session_state["video_bytes"] = b"abc"
        app.session_state["video_name"] = "test.mp4"
        app.run()
        self.assertFalse(app.exception)
        snippets = [item.value for item in app.code]
        self.assertIn("科研视频标题", snippets)
        self.assertIn("可复制的科研视频文案", snippets)

    def test_large_local_video_does_not_copy_into_session_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "large.mp4"
            with source.open("wb") as handle:
                handle.truncate(201 * 1024**2)
            app = self.launch()
            next(x for x in app.text_input if x.label.startswith("本机视频路径")).set_value(str(source))
            next(x for x in app.text_input if x.label == "视频标题").set_value("Local research video")
            app.multiselect[0].select("YouTube")
            with patch.object(Path, "write_bytes"):
                next(x for x in app.button if x.label == "检查稿件").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state["video_local_path"], str(source.resolve()))
            self.assertEqual(app.session_state["video_bytes"], b"")
            self.assertEqual(app.session_state["video_post"]["video_size_bytes"], 201 * 1024**2)

    def test_local_source_kept_and_temporary_upload_removed_on_error(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "original.mp4"
            source.write_bytes(b"original")
            with video_path("original.mp4", b"", str(source)) as path:
                self.assertEqual(path, str(source.resolve()))
            self.assertTrue(source.exists())
        with self.assertRaises(RuntimeError):
            with video_path("upload.mp4", b"upload") as path:
                self.assertTrue(Path(path).exists())
                raise RuntimeError("Simulated API failure")
        self.assertFalse(Path(path).exists())

    def test_youtube_setup_and_authorization_do_not_upload_video(self):
        config = {"installed": {
            "client_id": "test-client", "client_secret": "test-secret",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }}
        with tempfile.TemporaryDirectory() as directory, patch.object(youtube, "__file__", str(Path(directory) / "youtube.py")):
            with self.assertRaises(ValueError):
                youtube.save_client_config(b'{"key": "not-an-oauth-client"}')
            youtube.save_client_config(json.dumps(config).encode())
            self.assertEqual((Path(directory) / "client_secret.json").stat().st_mode & 0o777, 0o600)
            credentials = Credentials("test-token")
            with patch("google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file") as flow, patch("googleapiclient.discovery.build") as build:
                flow.return_value.run_local_server.return_value = credentials
                self.assertIs(youtube.authorize_youtube(), credentials)
                build.assert_not_called()
            self.assertEqual((Path(directory) / "youtube_token.json").stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
