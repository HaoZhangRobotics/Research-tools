"""Optional official YouTube Data API upload integration."""
from pathlib import Path
import json
import os


def _save_private(path: Path, text: str) -> None:
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as handle:
        handle.write(text)
    path.chmod(0o600)


def save_client_config(raw: bytes) -> None:
    config = json.loads(raw)
    installed = config.get("installed", {})
    if not installed.get("client_id") or not installed.get("client_secret"):
        raise ValueError("请选择 Google Cloud 下载的 OAuth 桌面应用 JSON，API key 或 Web 应用凭据不适用。")
    if installed.get("auth_uri") != "https://accounts.google.com/o/oauth2/auth" or installed.get("token_uri") != "https://oauth2.googleapis.com/token":
        raise ValueError("凭据中的 Google OAuth 地址不正确，请重新从 Google Cloud 下载。")
    root = Path(__file__).resolve().parent
    if (root / "youtube_token.json").exists():
        raise ValueError("已有 YouTube 授权记录；请先断开旧授权，再更换应用凭据。")
    _save_private(root / "client_secret.json", json.dumps(config))


def authorize_youtube():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise RuntimeError("缺少 YouTube 可选依赖，请安装 video_publisher/requirements-youtube.txt") from exc
    root = Path(__file__).resolve().parent
    client_file, token_file = root / "client_secret.json", root / "youtube_token.json"
    if not client_file.exists():
        raise RuntimeError("请将 Google Cloud OAuth 桌面应用凭据保存为 tools/video_publisher/client_secret.json")
    scopes = ["https://www.googleapis.com/auth/youtube.upload"]
    credentials = Credentials.from_authorized_user_file(str(token_file), scopes) if token_file.exists() else None
    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    if not credentials or not credentials.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(client_file), scopes)
        credentials = flow.run_local_server(port=0, open_browser=True, timeout_seconds=180)
    _save_private(token_file, credentials.to_json())
    return credentials


def upload_video(video_path: str, title: str, description: str, tags: list[str], privacy: str) -> str:
    if len(title) > 100:
        raise ValueError("YouTube 标题不能超过 100 个字符，请缩短标题后重试。")
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    credentials = authorize_youtube()
    youtube = build("youtube", "v3", credentials=credentials)
    snippet = {"title": title, "description": description, "categoryId": "28"}
    if tags:
        snippet["tags"] = tags
    body = {"snippet": snippet, "status": {"privacyStatus": privacy}}
    media = MediaFileUpload(video_path, mimetype="video/*", chunksize=8 * 1024 * 1024, resumable=True)
    response = youtube.videos().insert(part="snippet,status", body=body, media_body=media).execute()
    return response["id"]
