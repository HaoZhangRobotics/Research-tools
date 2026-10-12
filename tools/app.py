"""Unified local research tools launcher."""
import streamlit as st

st.set_page_config(page_title="Research Tools", page_icon="🧪", layout="wide")

pages = [
    st.Page("home.py", title="工作台", icon="🧪", default=True),
    st.Page("paper_crawler/app.py", title="作者论文采集", icon="📚"),
    st.Page("conference_crawler/app.py", title="会议论文采集", icon="📑"),
    st.Page("video_publisher/app.py", title="科研视频发布", icon="🎬"),
]
st.navigation(pages).run()
