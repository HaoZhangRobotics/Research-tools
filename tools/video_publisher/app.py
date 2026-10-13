"""Prepare research video posts and publish to configured official APIs."""
from datetime import datetime
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
PLATFORMS = {
    "抖音": ("https://open.douyin.com/", "已接入官方上传与发布 API；需应用通过审核并在本机配置获批的 video.create 用户授权。"),
    "哔哩哔哩": ("https://open.bilibili.com/doc/main", "开放平台提供稿件分发能力，需开发者认证及对应应用权限；此工具暂未接入官方投稿 API。"),
    "小红书": ("https://open.xiaohongshu.com/", "当前开放平台文档覆盖登录授权等接口；未确认面向通用创作者的视频投稿 API，先生成稿件包。"),
    "X": ("https://developer.x.com/en/docs", "视频发布需要获批的 X API 访问权限及媒体上传授权；此工具暂未接入 X 媒体上传。"),
    "YouTube": ("https://studio.youtube.com/", "支持 YouTube Data API 官方上传；需配置 Google Cloud OAuth 桌面应用凭据。"),
}

st.set_page_config(page_title="科研视频发布", page_icon="🎬", layout="wide")
st.title("🎬 科研视频发布")
st.caption("整理视频稿件、选择目标平台。只有配置官方 API 的平台才会直发；其他平台可下载稿件并打开创作者后台。")

with st.expander("账号授权与连接（首次使用先设置）"):
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
    st.markdown("**抖音**")
    st.write("先在抖音开放平台注册应用并获批 video.create 发布权限，再按该应用的 OAuth 流程让自己的抖音账号授权，获得用户 access_token 和 open_id。当前工具不会自动完成抖音应用申请或登录授权。")
    st.link_button("打开抖音开放平台", "https://open.douyin.com/")
    st.write("把这两个值保存到项目根目录的 .streamlit/secrets.toml：")
    st.code('douyin_access_token = "你的用户授权 access_token"\ndouyin_open_id = "对应账号 open_id"', language="toml")
    st.caption("B 站、小红书和 X 当前尚未接入账号授权与直发。")

with st.form("video_post_form"):
    video = st.file_uploader("视频文件（本地界面上限 2 GB）", type=["mp4", "mov", "m4v", "webm", "avi"], max_upload_size=2048)
    local_path = st.text_input("本机视频路径（可选，大视频推荐）", placeholder="/Users/zhanghao/Desktop/科研视频.mp4", help="填入路径时优先使用本机文件，不经浏览器复制进内存，也不受界面的 2 GB 上传限制；平台自身限制仍适用。")
    title = st.text_area("视频标题", height=70, key="publisher_title", help="可以直接粘贴完整标题。粘贴中的换行会在检查稿件时合并为一行，平台长度限制会在发布前检查。")
    description = st.text_area("视频简介 / 文案", height=180, max_chars=5000)
    tag_text = st.text_input("标签（逗号分隔）", placeholder="robotics, research, 科研")
    selected = st.multiselect("发布平台", list(PLATFORMS), default=[])
    privacy = st.selectbox("YouTube 隐私状态", ["private", "unlisted", "public"], index=0,
                           help="默认为私享；公开发布前请先确认频道和视频内容。")
    submitted = st.form_submit_button("检查稿件", type="primary")

ready = st.checkbox("我已检查视频、标题、文案和目标平台；点击发布会向所选且已配置的平台发送内容。")

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
            "tags": tags, "platforms": selected, "youtube_privacy": privacy}
    st.session_state.video_post = post
    st.session_state.video_bytes = b"" if source else video.getvalue()
    st.session_state.video_name = post["video_filename"]
    st.session_state.video_local_path = str(source) if source else ""

post = st.session_state.get("video_post")
if post:
    st.subheader("发布预览")
    st.caption("标题和文案均可点击右上角的复制按钮。")
    st.markdown("**标题**")
    st.code(post["title"], language=None, wrap_lines=True)
    st.write(f"**视频：** {post['video_filename']} · {post['video_size_bytes'] / 1024**2:.1f} MB")
    st.write(f"**目标：** {'、'.join(post['platforms'])}")
    st.markdown("**文案**")
    st.code(post["description"], language=None, wrap_lines=True, height=200)
    payload = json.dumps(post, ensure_ascii=False, indent=2).encode("utf-8")
    st.download_button("下载稿件 JSON", payload, "research-video-post.json", "application/json")
    output = ROOT / "output"
    output.mkdir(exist_ok=True)
    if submitted:
        draft_path = output / f"post_{datetime.now():%Y%m%d_%H%M%S}.json"
        draft_path.write_bytes(payload)

    if "YouTube" in post["platforms"]:
        st.markdown("#### YouTube")
        title_ok = len(post["title"]) <= 100
        if not title_ok:
            st.warning(f"标题已完整保留（{len(post['title'])} 个字符）。YouTube 最多允许 100 个字符，请修改上方标题并重新点击“检查稿件”后再发布。")
        client_ready = (ROOT / "client_secret.json").exists()
        if not client_ready:
            st.info("尚未配置 OAuth 凭据。按 README 配好 Google Cloud 桌面应用后，这里即可授权并直传。")
        if st.button("发布到 YouTube", disabled=(not ready or not client_ready or not title_ok), type="primary"):
            try:
                from video_publisher.youtube import upload_video
                with video_path(st.session_state.video_name, st.session_state.video_bytes, st.session_state.get("video_local_path", "")) as temp_path, st.spinner("正在通过 YouTube 官方 API 上传…"):
                    video_id = upload_video(temp_path, post["title"], post["description"], post["tags"], post["youtube_privacy"])
                st.success(f"上传成功，Video ID：{video_id}")
                st.link_button("打开 YouTube 视频", f"https://youtu.be/{video_id}")
            except Exception as exc:
                st.error(f"上传失败：{exc}")

    if "抖音" in post["platforms"]:
        st.markdown("#### 抖音")
        try:
            dy_token = st.secrets.get("douyin_access_token", "")
            dy_open_id = st.secrets.get("douyin_open_id", "")
        except Exception:
            dy_token, dy_open_id = "", ""
        douyin_ready = bool(dy_token and dy_open_id and st.session_state.video_post["video_size_bytes"] <= 128 * 1024**2)
        if not dy_token or not dy_open_id:
            st.info("本机尚未配置抖音 access_token 和 open_id。请先完成开放平台应用审核和用户授权，再按 README 存入本地 secrets。")
        elif not douyin_ready:
            st.warning("当前直接上传入口限制为 128 MB 以内的视频；更大视频请使用抖音创作者后台。")
        if st.button("发布到抖音", disabled=(not ready or not douyin_ready), type="primary"):
            try:
                from video_publisher.douyin import publish_video
                with video_path(st.session_state.video_name, st.session_state.video_bytes, st.session_state.get("video_local_path", "")) as temp_path, st.spinner("正在通过抖音开放平台上传并提交审核…"):
                    item_id = publish_video(temp_path, post["title"], dy_token, dy_open_id)
                st.success(f"抖音已接收发布请求：{item_id}。平台审核期间可能只有自己可见。")
            except Exception as exc:
                st.error(f"抖音发布失败：{exc}")

    manual = [name for name in post["platforms"] if name not in ("YouTube", "抖音")]
    if manual:
        st.markdown("#### 其他平台")
        st.caption("稿件已整理好。以下平台暂时不会通过非官方方式模拟登录或投稿；请使用官方创作者后台完成最终发布。")
        if st.session_state.get("video_local_path"):
            st.caption(f"原视频位于本机：{st.session_state.video_local_path}")
        else:
            st.download_button("下载原视频文件", st.session_state.video_bytes,
                               st.session_state.video_name, key="download_original_video")
        for name in manual:
            url, note = PLATFORMS[name]
            st.write(f"**{name}** — {note}")
            st.link_button(f"打开 {name} 官方入口", url, key=f"platform_{name}")
