"""Unified local research tools launcher."""
import sys
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Research Tools", page_icon="🧪", layout="wide")
TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

pages = [
    st.Page("home.py", title="工作台", icon="🧪", url_path="home", default=True),
    st.Page("paper_crawler/app.py", title="作者论文采集", icon="📚", url_path="author-papers"),
    st.Page("conference_crawler/app.py", title="会议论文采集", icon="📑", url_path="conference-papers"),
    st.Page("video_publisher/app.py", title="科研视频发布", icon="🎬", url_path="video-publisher"),
]
st.navigation(pages).run()
