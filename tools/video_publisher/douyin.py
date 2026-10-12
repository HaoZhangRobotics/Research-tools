"""Minimal Douyin Open Platform upload and publish adapter."""
import mimetypes
import requests


def publish_video(video_path: str, title: str, access_token: str, open_id: str) -> str:
    headers = {"access-token": access_token}
    mime_type = mimetypes.guess_type(video_path)[0] or "application/octet-stream"
    with open(video_path, "rb") as video_file:
        uploaded = requests.post(
            "https://open.douyin.com/video/upload/",
            params={"open_id": open_id}, headers=headers,
            files={"video": (video_path.rsplit("/", 1)[-1], video_file, mime_type)}, timeout=(30, 900),
        )
    uploaded.raise_for_status()
    upload_data = uploaded.json().get("data", {})
    if upload_data.get("error_code") != 0 or not upload_data.get("video", {}).get("video_id"):
        raise RuntimeError(uploaded.json().get("extra", {}).get("description") or upload_data.get("description") or "抖音视频上传失败")
    response = requests.post(
        "https://open.douyin.com/video/create/", params={"open_id": open_id}, headers=headers,
        json={"video_id": upload_data["video"]["video_id"], "text": title}, timeout=60,
    )
    response.raise_for_status()
    result = response.json()
    data = result.get("data", {})
    if data.get("error_code") != 0:
        raise RuntimeError(result.get("extra", {}).get("description") or data.get("description") or "抖音发布失败")
    return data.get("item_id", "已提交审核")
