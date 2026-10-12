"""Prepare research video posts and publish to configured official APIs."""
from datetime import datetime
import json
from pathlib import Path
import re
import tempfile

import streamlit as st

ROOT = Path(__file__).resolve().parent
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

with st.form("video_post"):
    video = st.file_uploader("视频文件", type=["mp4", "mov", "m4v", "webm", "avi"])
    title = st.text_input("视频标题", max_chars=100)
    description = st.text_area("视频简介 / 文案", height=180, max_chars=5000)
    tag_text = st.text_input("标签（逗号分隔）", placeholder="robotics, research, 科研")
    selected = st.multiselect("发布平台", list(PLATFORMS), default=[])
    privacy = st.selectbox("YouTube 隐私状态", ["private", "unlisted", "public"], index=0,
                           help="默认为私享；公开发布前请先确认频道和视频内容。")
    submitted = st.form_submit_button("检查稿件", type="primary")

ready = st.checkbox("我已检查视频、标题、文案和目标平台；点击发布会向所选且已配置的平台发送内容。")

if submitted:
    errors = []
    if not video:
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
    post = {"created_at": datetime.now().astimezone().isoformat(), "video_filename": video.name,
            "video_size_bytes": video.size, "title": title.strip(), "description": description.strip(),
            "tags": tags, "platforms": selected, "youtube_privacy": privacy}
    st.session_state.video_post = post
    st.session_state.video_bytes = video.getvalue()
    st.session_state.video_name = video.name

post = st.session_state.get("video_post")
if post:
    st.subheader("发布预览")
    st.write(f"**标题：** {post['title']}")
    st.write(f"**视频：** {post['video_filename']} · {post['video_size_bytes'] / 1024**2:.1f} MB")
    st.write(f"**目标：** {'、'.join(post['platforms'])}")
    st.text_area("文案预览", post["description"], height=130, disabled=True)
    payload = json.dumps(post, ensure_ascii=False, indent=2).encode("utf-8")
    st.download_button("下载稿件 JSON", payload, "research-video-post.json", "application/json")
    output = ROOT / "output"
    output.mkdir(exist_ok=True)
    if submitted:
        draft_path = output / f"post_{datetime.now():%Y%m%d_%H%M%S}.json"
        draft_path.write_bytes(payload)

    if "YouTube" in post["platforms"]:
        st.markdown("#### YouTube")
        client_ready = (ROOT / "client_secret.json").exists()
        if not client_ready:
            st.info("尚未配置 OAuth 凭据。按 README 配好 Google Cloud 桌面应用后，这里即可授权并直传。")
        if st.button("发布到 YouTube", disabled=(not ready or not client_ready), type="primary"):
            with tempfile.NamedTemporaryFile(suffix=Path(st.session_state.video_name).suffix, delete=False) as handle:
                handle.write(st.session_state.video_bytes)
                temp_path = handle.name
            try:
                from youtube import upload_video
                with st.spinner("正在通过 YouTube 官方 API 上传…"):
                    video_id = upload_video(temp_path, post["title"], post["description"], post["tags"], post["youtube_privacy"])
                st.success(f"上传成功，Video ID：{video_id}")
                st.link_button("打开 YouTube 视频", f"https://youtu.be/{video_id}")
            except Exception as exc:
                st.error(f"上传失败：{exc}")
            finally:
                Path(temp_path).unlink(missing_ok=True)

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
            with tempfile.NamedTemporaryFile(suffix=Path(st.session_state.video_name).suffix, delete=False) as handle:
                handle.write(st.session_state.video_bytes)
                temp_path = handle.name
            try:
                from douyin import publish_video
                with st.spinner("正在通过抖音开放平台上传并提交审核…"):
                    item_id = publish_video(temp_path, post["title"], dy_token, dy_open_id)
                st.success(f"抖音已接收发布请求：{item_id}。平台审核期间可能只有自己可见。")
            except Exception as exc:
                st.error(f"抖音发布失败：{exc}")
            finally:
                Path(temp_path).unlink(missing_ok=True)

    manual = [name for name in post["platforms"] if name not in ("YouTube", "抖音")]
    if manual:
        st.markdown("#### 其他平台")
        st.caption("稿件已整理好。以下平台暂时不会通过非官方方式模拟登录或投稿；请使用官方创作者后台完成最终发布。")
        st.download_button("下载原视频文件", st.session_state.video_bytes,
                           st.session_state.video_name, key="download_original_video")
        for name in manual:
            url, note = PLATFORMS[name]
            st.write(f"**{name}** — {note}")
            st.link_button(f"打开 {name} 官方入口", url, key=f"platform_{name}")
