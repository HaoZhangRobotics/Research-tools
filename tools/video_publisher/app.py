"""Prepare research video posts and publish to configured official APIs."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys

import streamlit as st

ROOT = Path(__file__).resolve().parent
TOOLS_DIR = ROOT.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
from video_publisher.media import local_video, video_path
from video_publisher.browser_publish import BROWSER_PLATFORMS, login_browser, profile_dir
from video_publisher.publish_queue import publish_selected
PLATFORMS = {
    "抖音": (BROWSER_PLATFORMS["抖音"]["url"], "默认使用本机浏览器发布；也可选官方 API。"),
    "哔哩哔哩": (BROWSER_PLATFORMS["哔哩哔哩"]["url"], "使用本机专用 Chrome 上传视频并投稿。"),
    "小红书": (BROWSER_PLATFORMS["小红书"]["url"], "使用本机专用 Chrome 上传视频并发布笔记。"),
    "X": (BROWSER_PLATFORMS["X"]["url"], "使用本机专用 Chrome 上传视频并发帖。"),
    "YouTube": ("https://studio.youtube.com/", "支持 YouTube Data API 官方上传；需配置 Google Cloud OAuth 桌面应用凭据。"),
}
PLATFORM_LABELS = {"哔哩哔哩": "B站（哔哩哔哩）"}


def platform_label(name):
    return PLATFORM_LABELS.get(name, name)

st.set_page_config(page_title="科研视频发布", page_icon="🎬", layout="wide")
st.title("🎬 科研视频发布")
st.caption("勾选要发布的平台，检查稿件并确认后统一发送。各平台分别返回结果；未勾选的平台不会收到内容。")
st.info("浏览器发布适配器已加入，平台页面流程尚需用你的账号实测。验证码由你在浏览器完成；工具不会绕过验证码，也不会把未确认的提交显示为成功。")

with st.expander("登录与授权（首次发布先连接账号）"):
    st.write("抖音、B站、小红书和 X 使用各自的专用浏览器。点击登录，在新窗口正常登录或扫码；登录完成后关闭该专用窗口，再回这里发布。浏览器登录状态只保存在本机。")
    for name in BROWSER_PLATFORMS:
        if st.button(f"登录 {platform_label(name)}", key=f"login_{name}"):
            try:
                process_id = login_browser(name)
                st.info(f"已启动专用浏览器（任务 {process_id}）。登录后关闭该窗口；若窗口没出现，请查看 {profile_dir(name) / 'login.log'}。")
            except Exception as exc:
                st.error(f"浏览器未启动：{exc}")
        if (profile_dir(name) / "session_saved.json").exists():
            st.caption(f"{platform_label(name)} 已保存浏览器会话；登录有效性将在发布时检查。")
    st.markdown("**YouTube**")
    st.write("在 Google Cloud 启用 YouTube Data API v3，配置 OAuth 同意屏幕；若项目处于测试模式，添加自己的 Google 账号为测试用户。创建类型为“桌面应用”的 OAuth 客户端，并下载 JSON。")
    st.link_button("打开 Google Cloud 凭据页面", "https://console.cloud.google.com/apis/credentials")
    client_json = st.file_uploader("导入 YouTube OAuth 桌面应用 JSON", type=["json"], key="youtube_client_json", max_upload_size=1)
    if st.button("保存 YouTube 应用凭据", disabled=client_json is None):
        try:
            from video_publisher.youtube import save_client_config
            save_client_config(client_json.getvalue())
            st.success("应用凭据已保存在本机，下一步点击“登录并授权 YouTube”。")
        except (ValueError, OSError) as exc:
            st.error(str(exc))
    if st.button("登录并授权 YouTube", disabled=not (ROOT / "client_secret.json").exists()):
        try:
            from video_publisher.youtube import authorize_youtube
            with st.spinner("请在打开的 Google 页面选择频道账号并同意授权，3 分钟内完成。此步骤不会上传视频。"):
                authorize_youtube()
            st.success("YouTube 授权已保存。现在可以准备稿件并点击发布。")
        except Exception as exc:
            st.error(f"授权未完成：{exc}")
    if (ROOT / "youtube_token.json").exists():
        st.caption("本机已有授权记录，有效性会在授权或上传时检查。")
        if st.button("清除本机 YouTube 授权记录"):
            (ROOT / "youtube_token.json").unlink(missing_ok=True)
            st.rerun()
        st.caption("清除本机记录不会撤销 Google 侧授权。")
    if st.checkbox("显示抖音官方 API 高级设置（可选）"):
        st.write("默认浏览器发布不需要这些值。仅在选择“官方 API”时，需要获批 video.create 权限并把真实授权值保存在 .streamlit/secrets.toml；示例文字不是可用凭据。")
        st.code('douyin_access_token = "替换为真实的用户授权 token"\ndouyin_open_id = "替换为对应账号的 open_id"', language="toml")
        st.link_button("打开抖音开放平台", "https://open.douyin.com/")

st.markdown("**选择发布平台（可多选，默认不选）**")
selected = []
for column, name in zip(st.columns(5), PLATFORMS):
    if column.checkbox(platform_label(name), value=False, key=f"publish_to_{name}"):
        selected.append(name)

with st.form("video_post_form"):
    video = st.file_uploader("视频文件（本地界面上限 2 GB）", type=["mp4", "mov", "m4v", "webm", "avi"], max_upload_size=2048)
    local_path = st.text_input("本机视频路径（可选，大视频推荐）", placeholder="/Users/zhanghao/Desktop/科研视频.mp4", help="填入路径时优先使用本机文件，不经浏览器复制进内存，也不受界面的 2 GB 上传限制；平台自身限制仍适用。")
    title = st.text_area("视频标题", height=70, key="publisher_title", help="可以直接粘贴完整标题。粘贴中的换行会在检查稿件时合并为一行，平台长度限制会在发布前检查。")
    description = st.text_area("视频简介 / 文案", height=180, max_chars=5000)
    tag_text = st.text_input("标签（逗号分隔）", placeholder="robotics, research, 科研")
    with st.expander("各平台稿件与发布方式（可选）"):
        bilibili_title = st.text_input("B站专用标题（留空使用通用标题）")
        xhs_title = st.text_input("小红书专用标题（留空使用通用标题）")
        youtube_title = st.text_input("YouTube 专用标题（留空使用通用标题）")
        x_text = st.text_area("X 专用文案（留空使用通用标题＋标签）", height=100)
        douyin_mode = st.selectbox("抖音发布方式", ["浏览器登录发布", "官方 API"], index=0)
    privacy = st.selectbox("YouTube 隐私状态", ["private", "unlisted", "public"], index=0,
                           help="默认为私享；公开发布前请先确认频道和视频内容。")
    submitted = st.form_submit_button("检查稿件", type="primary")

ready = st.checkbox("我已检查预览中的视频、各平台文案和勾选的平台，确认点击发布后发送。")

if submitted:
    title = " ".join(line.strip() for line in title.splitlines() if line.strip())
    errors = []
    source = None
    if local_path.strip():
        try:
            source = local_video(local_path)
        except ValueError as exc:
            errors.append(str(exc))
    if not video and not local_path.strip():
        errors.append("请选择视频文件。")
    if not title.strip():
        errors.append("请填写标题。")
    if not selected:
        errors.append("至少选择一个平台。")
    if errors:
        for error in errors:
            st.error(error)
        st.stop()
    tags = [tag.strip().lstrip("#") for tag in re.split(r"[,，;；]", tag_text) if tag.strip()]
    post = {"created_at": datetime.now().astimezone().isoformat(), "video_filename": source.name if source else video.name,
            "video_size_bytes": source.stat().st_size if source else video.size, "title": title.strip(), "description": description.strip(),
            "tags": tags, "platforms": selected, "youtube_privacy": privacy,
            "platform_titles": {"哔哩哔哩": bilibili_title.strip(), "小红书": xhs_title.strip(), "YouTube": youtube_title.strip()},
            "x_text": x_text.strip(), "douyin_mode": "api" if douyin_mode == "官方 API" else "browser"}
    st.session_state.video_post = post
    st.session_state.video_bytes = b"" if source else video.getvalue()
    st.session_state.video_name = post["video_filename"]
    st.session_state.video_local_path = str(source) if source else ""
    identity = {key: value for key, value in post.items() if key not in {"created_at", "platforms"}}
    video_identity = f"{source}:{source.stat().st_mtime_ns}".encode() if source else hashlib.sha256(st.session_state.video_bytes).digest()
    st.session_state.publisher_job_id = hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True).encode() + video_identity).hexdigest()[:32]
    st.session_state.pop("publisher_receipts", None)

post = st.session_state.get("video_post")
if post:
    st.subheader("发布预览")
    st.caption("标题和文案均可点击右上角的复制按钮。")
    st.markdown("**标题**")
    st.code(post["title"], language=None, wrap_lines=True)
    st.write(f"**视频：** {post['video_filename']} · {post['video_size_bytes'] / 1024**2:.1f} MB")
    st.write(f"**目标：** {'、'.join(platform_label(name) for name in post['platforms'])}")
    st.markdown("**文案**")
    st.code(post["description"], language=None, wrap_lines=True, height=200)
    payload = json.dumps(post, ensure_ascii=False, indent=2).encode("utf-8")
    st.download_button("下载稿件 JSON", payload, "research-video-post.json", "application/json")
    output = ROOT / "output"
    output.mkdir(exist_ok=True)
    if submitted:
        draft_path = output / f"post_{datetime.now():%Y%m%d_%H%M%S}.json"
        draft_path.write_bytes(payload)

    for name in post["platforms"]:
        platform_title = post.get("platform_titles", {}).get(name) or post["title"]
        if name == "YouTube" and len(platform_title) > 100:
            st.warning(f"标题已完整保留（{len(platform_title)} 个字符）。YouTube 最多允许 100 个字符，请修改 YouTube 专用标题并重新检查稿件。")
        if name == "X":
            text = post.get("x_text") or "\n".join(part for part in [post["title"], " ".join("#" + tag for tag in post["tags"])] if part)
            st.markdown("**X 本次实际文案**")
            st.code(text, language=None, wrap_lines=True)
        elif platform_title != post["title"]:
            st.markdown(f"**{platform_label(name)} 本次专用标题**")
            st.code(platform_title, language=None, wrap_lines=True)
        st.caption(f"{platform_label(name)}：{PLATFORMS[name][1]}")

    selection_matches = selected == post["platforms"]
    if not selection_matches:
        st.warning("平台勾选已改变，请重新点击“检查稿件”，核对新的目标平台后再发布。")
    if st.button("发布到勾选的平台", disabled=(not ready or not selection_matches), type="primary"):
        try:
            try:
                credentials = (st.secrets.get("douyin_access_token", ""), st.secrets.get("douyin_open_id", ""))
            except Exception:
                credentials = ("", "")
            job_id = st.session_state.get("publisher_job_id")
            if not job_id:
                st.error("请先重新点击“检查稿件”，再发布。")
            else:
                progress = st.empty()
                with video_path(st.session_state.video_name, st.session_state.video_bytes, st.session_state.get("video_local_path", "")) as filename:
                    receipts = publish_selected(post, filename, job_id, credentials,
                        notify=lambda name: progress.info(f"正在处理 {platform_label(name)}，请等待；未勾选的平台不会运行。"))
                st.session_state.publisher_receipts = receipts
                progress.empty()
        except Exception as exc:
            st.error(f"发布任务未完成：{exc}")

    if st.session_state.get("publisher_receipts"):
        labels = {"submitted": "已提交", "failed": "失败", "unknown": "待核查", "sending": "中断待核查"}
        st.subheader("各平台发布结果")
        for name in post["platforms"]:
            receipt = st.session_state.publisher_receipts.get(name, {})
            state = receipt.get("state", "unknown")
            display = f"{platform_label(name)} · {labels.get(state, state)}：{receipt.get('message', '')}"
            if state == "submitted":
                st.success(display)
            elif state == "failed":
                st.error(display)
            else:
                st.warning(display)
            if receipt.get("url"):
                st.link_button(f"查看 {platform_label(name)} 稿件", receipt["url"], key=f"receipt_{name}")
        st.caption("再次点击会跳过已提交或结果不明的平台，避免重复发帖；明确失败的项可以在修复登录或稿件后重试。")
