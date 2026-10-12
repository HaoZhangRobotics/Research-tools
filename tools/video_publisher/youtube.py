"""Optional official YouTube Data API upload integration."""
from pathlib import Path


def upload_video(video_path: str, title: str, description: str, tags: list[str], privacy: str) -> str:
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
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
        credentials = flow.run_local_server(port=0, open_browser=True)
        token_file.write_text(credentials.to_json(), encoding="utf-8")
    youtube = build("youtube", "v3", credentials=credentials)
    snippet = {"title": title, "description": description, "categoryId": "28"}
    if tags:
        snippet["tags"] = tags
    body = {"snippet": snippet, "status": {"privacyStatus": privacy}}
    media = MediaFileUpload(video_path, mimetype="video/*", chunksize=8 * 1024 * 1024, resumable=True)
    response = youtube.videos().insert(part="snippet,status", body=body, media_body=media).execute()
    return response["id"]
