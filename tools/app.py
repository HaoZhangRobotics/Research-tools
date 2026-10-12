"""Unified local research tools launcher."""
import streamlit as st

st.set_page_config(page_title="Research Tools", page_icon="🧪", layout="wide")

pages = [
    st.Page("home.py", title="工作台", icon="🧪", url_path="home", default=True),
    st.Page("paper_crawler/app.py", title="作者论文采集", icon="📚", url_path="author-papers"),
    st.Page("conference_crawler/app.py", title="会议论文采集", icon="📑", url_path="conference-papers"),
    st.Page("video_publisher/app.py", title="科研视频发布", icon="🎬", url_path="video-publisher"),
]
st.navigation(pages).run()
