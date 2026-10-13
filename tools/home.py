import streamlit as st

st.title("🧪 Research Tools")
st.caption("选择一个工具开始工作。所有工具都在本机运行，采集结果和发布素材保存在本地。")

cards = [
    ("📚 作者论文采集", "查找 Google Scholar 作者；按年份和关键词筛选论文，汇总信息并下载可获取的 PDF。"),
    ("📑 会议论文采集", "从 RSS 等会议目录采集标题、作者、摘要、BibTeX 和公开 PDF，支持失败重试。"),
    ("🎬 科研视频发布", "勾选抖音、B站、小红书、X 或 YouTube，登录或授权后统一发布，各平台分别显示结果。浏览器发布适配器已加入，仍需账号实测。"),
]
for title, description in cards:
    with st.container(border=True):
        st.subheader(title)
        st.write(description)
st.info("从左侧导航栏选择工具。启动命令：`streamlit run tools/app.py`。")
