"""Per-platform posting receipts; don't resend successful or ambiguous jobs."""
import json
import fcntl
from pathlib import Path
import re

from video_publisher.browser_publish import publish_browser

ROOT = Path(__file__).resolve().parent


def publish_one(platform, video, post, douyin_credentials=None):
    if platform == "YouTube":
        if not (ROOT / "client_secret.json").exists():
            raise ValueError("请先在“登录与授权”中导入 YouTube OAuth 凭据并授权。")
        from video_publisher.youtube import upload_video
        title = post.get("platform_titles", {}).get(platform) or post["title"]
        identifier = upload_video(video, title, post["description"], post["tags"], post["youtube_privacy"])
        return {"state": "submitted", "message": "YouTube 已接收视频，等待处理", "url": f"https://youtu.be/{identifier}"}
    if platform == "抖音" and post.get("douyin_mode") == "api":
        from video_publisher.douyin import publish_video
        token, open_id = douyin_credentials or ("", "")
        if not token or not open_id:
            raise ValueError("抖音官方 API 尚未配置用户 token 和 open_id；可切换为浏览器登录发布。")
        if Path(video).stat().st_size > 128 * 1024**2:
            raise ValueError("当前抖音普通 API 上传限 128 MB，可改选浏览器发布。")
        text = "\n".join(part for part in [post["title"], post["description"], " ".join("#" + tag for tag in post["tags"])] if part)
        identifier = publish_video(video, text, token, open_id)
        return {"state": "submitted", "message": f"抖音已接收稿件，等待审核：{identifier}"}
    return publish_browser(platform, video, post)


def publish_selected(post, video, job_id, douyin_credentials=None, notify=None, publisher=None):
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise ValueError("发布任务 ID 无效。")
    publisher = publisher or publish_one
    directory = ROOT / "output" / "publish_jobs"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{job_id}.json"
    with path.with_suffix(".lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("该稿件正在另一个任务中发布，请等待完成，勿重复提交。")
        return _send_selected(post, video, path, douyin_credentials, notify, publisher)


def _send_selected(post, video, path, douyin_credentials, notify, publisher):
    records = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for platform in post["platforms"]:
        old = records.get(platform, {})
        if old.get("state") in {"submitted", "unknown", "sending"}:
            continue
        if notify:
            notify(platform)
        # Persist before invoking an external service. An interrupted attempt
        # remains ambiguous and is never automatically duplicated.
        records[platform] = {"state": "sending", "message": "正在提交；若任务中断，请先到平台核查。"}
        path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
        try:
            receipt = publisher(platform, video, post, douyin_credentials)
            if receipt.get("state") not in {"submitted", "unknown", "failed"}:
                receipt = {"state": "unknown", "message": "未获得明确的平台回执，请先到平台核查。"}
            records[platform] = receipt
        except ValueError as exc:
            records[platform] = {"state": "failed", "message": str(exc)}
        except Exception as exc:
            records[platform] = {"state": "unknown", "message": f"请求异常，不能确定平台是否收到，请先核查：{exc}"}
        path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return records
