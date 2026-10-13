"""Run: streamlit run tools/conference_crawler/app.py"""
from pathlib import Path
import sys
import zipfile

import streamlit as st

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from conference_crawler.crawler import DEFAULT_URL, crawl

st.set_page_config(page_title="会议论文采集器", page_icon="📑", layout="wide")
st.title("📑 会议论文采集器")
st.caption("采集会议目录中的全部论文信息、摘要、BibTeX 和公开 PDF。RSS 指 Robotics: Science and Systems 会议。")
with st.form("crawl"):
    url = st.text_input("会议论文目录网址", value=DEFAULT_URL)
    fetch_pdf = st.checkbox("下载全部公开 PDF", value=True)
    with st.expander("高级设置"):
        selector = st.text_input("论文链接 CSS 选择器（RSS 官网自动识别；其他会议必填）", placeholder="例如 a.paper-link")
        output = st.text_input("输出目录（留空自动生成；相同目录重新运行可重试失败项并跳过已下载 PDF）")
        delay = st.number_input("请求间隔（秒）", min_value=0.2, value=1.0, step=0.2)
    run = st.form_submit_button("全量采集", type="primary")
if run:
    st.session_state.pop("conference_zip", None)
    status = st.empty()
    try:
        directory, report = crawl(url, output.strip() or None, selector.strip() or None,
                                  fetch_pdf, delay, status.info)
        st.session_state.conference_result = (directory, report)
    except (ValueError, OSError) as exc:
        st.error(str(exc))
    finally:
        status.empty()

if "conference_result" in st.session_state:
    directory, report = st.session_state.conference_result
    papers = report["papers"]
    (st.success if report["state"] == "完成" else st.warning)(report["state"])
    st.caption(f"保存目录：{directory.resolve()}")
    a, b, c = st.columns(3)
    a.metric("论文数", len(papers))
    b.metric("PDF 已下载", sum(p["pdf_status"] == "downloaded" for p in papers))
    c.metric("详情失败", sum(p["detail_status"] == "failed" for p in papers))
    st.dataframe([{k: p[k] for k in ("title", "authors", "year", "venue", "pdf_status", "source_url", "detail_error", "pdf_error")} for p in papers],
                 width="stretch", column_config={"source_url": st.column_config.LinkColumn("论文原文")})
    for col, (name, mime) in zip(st.columns(3), [("papers.csv", "text/csv"), ("papers.json", "application/json"), ("papers.bib", "text/plain")]):
        if (directory / name).exists():
            col.download_button(f"下载 {name}", (directory / name).read_bytes(), name, mime)
    if st.button("生成完整 ZIP（大量 PDF 时可能较大）"):
        archive = directory / "papers.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED) as bundle:
            for path in sorted(directory.rglob("*")):
                if path.is_file() and path.suffix not in (".zip", ".part", ".tmp"):
                    bundle.write(path, path.relative_to(directory))
        st.session_state.conference_zip = archive
    archive = st.session_state.get("conference_zip")
    if archive and archive.parent == directory and archive.exists():
        st.caption(f"ZIP 已保存：{archive.resolve()}（{archive.stat().st_size / 1024**2:.0f} MB）；可直接在本地打开。")
        if archive.stat().st_size <= 200 * 1024**2:
            st.download_button("下载完整 ZIP", archive.read_bytes(), "papers.zip", "application/zip")
    st.subheader("论文详情")
    for p in papers:
        with st.expander(p["title"]):
            st.write(p["authors"])
            st.write(p["abstract"] or "未获取到摘要")
            st.link_button("来源页面", p["source_url"])
            if p["pdf_file"] and (directory / p["pdf_file"]).exists():
                st.caption(f"本地 PDF：{(directory / p['pdf_file']).resolve()}")
            if p["detail_error"] or p["pdf_error"]:
                st.warning(p["detail_error"] or p["pdf_error"])
