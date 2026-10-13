"""Run one headed browser task; publish only after the app supplied a reviewed job."""
import fcntl
import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from video_publisher.browser_publish import BROWSER_PLATFORMS, profile_dir
from video_publisher.network import browser_proxy


class PostingError(RuntimeError):
    pass


def publish_receipt(platform, url, body):
    """Only posting responses count, never an upload response or a mere click."""
    parsed = urlparse(url)
    if platform == "哔哩哔哩" and parsed.hostname == "member.bilibili.com" and "/x/vu/web/add" in parsed.path:
        if body.get("code") == 0:
            data = body.get("data", {})
            identifier = data.get("bvid") or data.get("aid")
            if identifier:
                link = f"https://www.bilibili.com/video/{data['bvid']}" if data.get("bvid") else f"https://www.bilibili.com/video/av{identifier}"
                return {"state": "submitted", "message": "稿件已提交，等待平台审核", "url": link}
    if platform == "X" and parsed.hostname in {"x.com", "api.x.com"} and parsed.path.endswith("/CreateTweet"):
        data = body.get("data", {}).get("create_tweet", {}).get("tweet_results", {}).get("result", {})
        identifier = data.get("rest_id")
        if identifier:
            return {"state": "submitted", "message": "帖子已提交", "url": f"https://x.com/i/status/{identifier}"}
    return None


def visible(page, locators, timeout=30000):
    deadline = time.monotonic() + timeout / 1000
    while time.monotonic() < deadline:
        for locator in locators:
            for item in locator.all():
                if item.is_visible():
                    return item
        page.wait_for_timeout(250)
    raise PostingError("未找到预期的投稿字段。请先在专用浏览器登录；若平台改版，需更新适配器。")


def fill_exact(locator, text):
    locator.fill(text)
    actual = locator.input_value() if locator.evaluate("e => ['INPUT', 'TEXTAREA'].includes(e.tagName)") else locator.inner_text()
    if actual.strip() != text.strip():
        raise PostingError("平台未完整接受标题或文案，可能超出长度限制；请缩短后重新检查稿件。")


def upload_input(page, platform):
    selectors = [
        'input[type="file"][accept*="video"]', 'input[type="file"][accept*=".mp4"]',
        'input[type="file"][accept*=".mov"]',
    ]
    if platform == "X":
        selectors.insert(0, 'input[type="file"][data-testid="fileInput"]')
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        for selector in selectors:
            candidates = page.locator(selector)
            if candidates.count():
                return candidates.first
        page.wait_for_timeout(250)
    raise PostingError("没有找到视频上传框；请完成登录，并确认账户拥有投稿权限。")


def wait_uploaded(page, platform, timeout=900000):
    from playwright.sync_api import expect
    if platform == "X":
        page.get_by_test_id("attachments").wait_for(state="visible", timeout=timeout)
        # X disables posting until the attachment finishes uploading.
        button = visible(page, [page.get_by_test_id("tweetButton"), page.get_by_test_id("tweetButtonInline")])
        expect(button).to_be_enabled(timeout=timeout)
    else:
        visible(page, [page.get_by_text(re.compile("上传完成|上传成功|重新上传|更换视频|替换视频"))], timeout=timeout)


def compose(page, platform, video, post):
    title = post.get("platform_titles", {}).get(platform) or post["title"]
    tags = " ".join("#" + tag for tag in post.get("tags", []))
    description = "\n".join(part for part in [post["description"], tags] if part)
    if platform == "X":
        text = post.get("x_text") or "\n".join(part for part in [title, tags] if part)
        editor = visible(page, [page.get_by_test_id("tweetTextarea_0")])
        fill_exact(editor, text)
    elif platform == "抖音":
        text = "\n".join(part for part in [title, description] if part)
        editor = visible(page, [page.get_by_placeholder(re.compile("作品描述|作品标题")), page.locator('[contenteditable="true"]')])
        fill_exact(editor, text)
    else:
        title_field = visible(page, [page.get_by_placeholder(re.compile("标题")), page.get_by_role("textbox", name=re.compile("标题"))], timeout=900000)
        fill_exact(title_field, title)
        if description:
            editor = visible(page, [page.get_by_placeholder(re.compile("简介|正文|描述")), page.locator('[contenteditable="true"]'), page.locator("textarea")])
            fill_exact(editor, description)
        if platform == "哔哩哔哩":
            # Tags are separate in Bilibili's creator form.
            field = page.get_by_placeholder(re.compile("标签"))
            if field.count() and field.first.is_visible():
                for tag in post.get("tags", []):
                    field.first.fill(tag)
                    field.first.press("Enter")
            chooser = page.get_by_text("请选择分区", exact=True)
            if chooser.count() and chooser.first.is_visible():
                chooser.first.click()
                visible(page, [page.get_by_text("知识", exact=True)]).click()
                visible(page, [page.get_by_text("科学科普", exact=True)]).click()
    return title


def post_with_browser(page, platform, video, post, confirmation_timeout=120, upload_timeout=900000):
    from playwright.sync_api import expect
    page.goto(BROWSER_PLATFORMS[platform]["url"], wait_until="domcontentloaded", timeout=60000)
    # A login or CAPTCHA must be completed by the user; never solve it here.
    page.wait_for_timeout(1500)
    upload_input(page, platform).set_input_files(video)
    if platform == "X":
        compose(page, platform, video, post)
        wait_uploaded(page, platform, upload_timeout)
    else:
        wait_uploaded(page, platform, upload_timeout)
        compose(page, platform, video, post)
    receipt = []
    def on_response(response):
        if response.request.method != "POST":
            return
        if not ("/x/vu/web/add" in response.url or response.url.endswith("/CreateTweet")):
            return
        try:
            result = publish_receipt(platform, response.url, response.json())
            if result:
                receipt.append(result)
        except Exception:
            pass
    page.on("response", on_response)
    if platform == "X":
        button = visible(page, [page.get_by_test_id("tweetButton"), page.get_by_test_id("tweetButtonInline")])
    else:
        names = "立即投稿|投稿|发布" if platform == "哔哩哔哩" else "发布|发布笔记"
        button = visible(page, [page.get_by_role("button", name=re.compile(f"^({names})$"))])
    expect(button).to_be_enabled(timeout=60000)
    clicked = False
    try:
        # A click may reach the platform even if the browser then reports an error.
        clicked = True
        button.click(timeout=30000)
        success = page.get_by_text(re.compile(r"^发布成功$|^投稿成功$|^稿件投递成功$|^Your post was sent\.?$|^你的帖子已发送$"))
        deadline = time.monotonic() + confirmation_timeout
        while time.monotonic() < deadline:
            if receipt:
                return receipt[0]
            if any(item.is_visible() for item in success.all()):
                return {"state": "submitted", "message": "平台页面已显示提交成功；可能仍需审核", "url": page.url}
            page.wait_for_timeout(500)
        return {"state": "unknown", "message": "已点击提交，但未获得平台成功回执。请先在平台检查稿件，避免重复发布。"}
    except Exception as exc:
        if clicked:
            return {"state": "unknown", "message": f"提交后连接中断，需在平台核查：{exc}"}
        raise


def main():
    action, argument = sys.argv[1:3]
    request = json.loads(Path(argument).read_text()) if action == "publish" else None
    platform = request["platform"] if request else argument
    profile = profile_dir(platform)
    result = {"state": "failed", "message": "任务未完成"}
    context = None
    try:
        with (profile / "worker.lock").open("w") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise PostingError("该平台的专用浏览器仍在使用中。登录完成后请关闭窗口，再发布。")
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                context = playwright.chromium.launch_persistent_context(str(profile), channel="chrome", headless=False, proxy=browser_proxy())
                page = context.pages[0] if context.pages else context.new_page()
                if action == "login":
                    page.goto(BROWSER_PLATFORMS[platform]["url"], wait_until="domcontentloaded", timeout=60000)
                    while not page.is_closed():
                        try:
                            page.wait_for_timeout(1000)
                        except Exception:
                            break
                    (profile / "session_saved.json").write_text(json.dumps({"state": "session_saved", "account_validated": False}))
                else:
                    try:
                        result = post_with_browser(page, platform, request["video"], request["post"])
                    except Exception as exc:
                        result = {"state": "failed", "message": str(exc)}
                        try:
                            screenshot = Path(argument).with_name("failure.png")
                            page.screenshot(path=str(screenshot), full_page=True)
                            result["screenshot"] = str(screenshot)
                        except Exception:
                            pass
                try:
                    context.close()
                except Exception:
                    pass
    except Exception as exc:
        result = {"state": "failed", "message": str(exc)}
    if request:
        Path(argument).with_name("result.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    elif result["state"] == "failed" and result["message"] != "任务未完成":
        print(result["message"], file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
