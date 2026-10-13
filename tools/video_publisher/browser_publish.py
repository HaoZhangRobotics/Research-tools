"""Visible browser posting workers with isolated, local account profiles."""
import json
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parent
BROWSER_PLATFORMS = {
    "哔哩哔哩": {"key": "bilibili", "url": "https://member.bilibili.com/platform/upload/video/frame"},
    "小红书": {"key": "xiaohongshu", "url": "https://creator.xiaohongshu.com/publish/publish?source=official&target=video"},
    "X": {"key": "x", "url": "https://x.com/compose/post"},
    "抖音": {"key": "douyin", "url": "https://creator.douyin.com/creator-micro/content/upload"},
}


def profile_dir(platform):
    path = ROOT / "output" / "browser_profiles" / BROWSER_PLATFORMS[platform]["key"]
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    return path


def login_browser(platform):
    """User logs in in a dedicated browser, never in their existing Chrome profile."""
    path = profile_dir(platform)
    log = path / "login.log"
    with log.open("ab") as handle:
        process = subprocess.Popen(
            [sys.executable, str(ROOT / "browser_worker.py"), "login", platform],
            stdout=handle, stderr=handle, start_new_session=True,
        )
    return process.pid


def publish_browser(platform, filename, post):
    directory = ROOT / "output" / "browser_jobs" / uuid.uuid4().hex
    directory.mkdir(parents=True)
    manifest = directory / "request.json"
    manifest.write_text(json.dumps({"platform": platform, "video": str(Path(filename).resolve()), "post": post}, ensure_ascii=False), encoding="utf-8")
    try:
        result = subprocess.run(
            [sys.executable, str(ROOT / "browser_worker.py"), "publish", str(manifest)],
            capture_output=True, text=True, timeout=1800,
        )
    except subprocess.TimeoutExpired:
        return {"state": "unknown", "message": "浏览器任务超时，请先到平台检查是否已发布，再决定是否重试。"}
    receipt = directory / "result.json"
    if receipt.exists():
        return json.loads(receipt.read_text(encoding="utf-8"))
    return {"state": "unknown", "message": "浏览器任务异常退出且没有回执，请先到平台核查是否提交：" + (result.stderr or result.stdout)[-600:]}
