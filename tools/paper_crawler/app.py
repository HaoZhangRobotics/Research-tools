"""Run with: streamlit run tools/paper_crawler/app.py"""
from datetime import datetime
from pathlib import Path
import re
import uuid
import zipfile

import streamlit as st

from crawler import (Blocked, CrawlError, ScholarClient, download_pdf,
                     export_results, matches, scholar_id)

st.set_page_config(page_title="科研论文采集器", page_icon="📚", layout="wide")
st.title("📚 科研论文采集器")
st.caption("从作者 Google Scholar 主页整理论文，下载可获取的 PDF。")

with st.form("author_search"):
    query = st.text_input("作者姓名、Google Scholar 主页或作者 ID", placeholder="例如：作者姓名 + 学校，或 https://scholar.google.com/citations?user=…")
    is_id = st.checkbox("输入的是作者 ID（主页链接会自动识别）")
    search = st.form_submit_button("查找作者")
if search:
    st.session_state.pop("authors", None)
    try:
        if not query.strip():
            raise ValueError("请先输入作者。")
        with st.spinner("正在查找作者…"):
            if is_id or "://" in query:
                aid = scholar_id(query)
                authors = [{"id": aid, "name": aid, "affiliation": "通过主页或 ID 指定", "interests": ""}]
            else:
                authors = ScholarClient().search_authors(query.strip())
        st.session_state.authors = authors
        if not authors:
            st.info("未找到作者，请增加学校信息或直接输入 Scholar 主页。")
    except (CrawlError, ValueError) as exc:
        st.error(str(exc))

if st.session_state.get("authors"):
    author = st.selectbox("选择作者（姓名搜索显示 Scholar 首页候选）", st.session_state.authors,
                          format_func=lambda a: f"{a['name']} · {a['affiliation']} · {a['id']}")
    st.write(f"研究兴趣：{author['interests'] or '未提供'}")
    st.link_button("查看作者主页", f"https://scholar.google.com/citations?user={author['id']}")
    with st.form("collect"):
        all_papers = st.checkbox("全爬（忽略年份和领域筛选）", value=True)
        a, b = st.columns(2)
        start = a.number_input("起始年份（0 表示不限）", min_value=0, max_value=2100, value=0)
        end = b.number_input("结束年份（0 表示不限）", min_value=0, max_value=2100, value=0)
        keywords_text = st.text_input("领域关键词（逗号分隔，任意一个匹配即可）", placeholder="robotics, reinforcement learning, 机器人")
        st.caption("匹配标题、摘要和发表渠道，不做语义分类或自动翻译；建议同时填写中英文关键词。限定年份时排除年份缺失的记录。")
        fetch_pdf = st.checkbox("汇总后自动下载 PDF", value=True)
        run = st.form_submit_button("开始采集", type="primary")
    if run:
        low, high = (None, None) if all_papers else (start or None, end or None)
        keywords = [] if all_papers else [s.strip() for s in re.split("[,，;；]", keywords_text) if s.strip()]
        if low and high and low > high:
            st.error("起始年份不能大于结束年份。")
        else:
            directory = Path(__file__).parent / "output" / f"{author['id']}_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}"
            client, raw, selected = ScholarClient(), [], []
            metadata = {"author": author, "created_at": datetime.now().astimezone().isoformat(),
                        "filters": {"start": low, "end": high, "keywords": keywords}, "state": "采集中",
                        "list_complete": False, "detail_failures": []}
            status = st.empty()
            table = st.empty()
            try:
                for paper in client.publications(author["id"]):
                    raw.append(paper)
                    status.info(f"正在读取论文列表：已发现 {len(raw)} 篇")
                    export_results(raw, directory / "source", metadata)
                metadata["list_complete"] = True
                for index, paper in enumerate(raw, 1):
                    status.info(f"正在补全信息：{index}/{len(raw)} · {paper.title}")
                    # Skip known years outside the requested range before detail requests.
                    if paper.year is not None and not matches(paper, low, high):
                        continue
                    try:
                        client.detail(paper)
                    except Blocked:
                        raise
                    except CrawlError as exc:
                        paper.error = str(exc)
                        metadata["detail_failures"].append(paper.id)
                    if matches(paper, low, high, keywords):
                        selected.append(paper)
                        export_results(selected, directory, metadata)
                    export_results(raw, directory / "source", metadata)
                # The list is displayed and saved before downloads begin.
                table.dataframe([{"年份": p.year, "标题": p.title, "作者": p.authors, "发表渠道": p.venue}
                                 for p in selected], width="stretch")
                if fetch_pdf:
                    for index, paper in enumerate(selected, 1):
                        status.info(f"正在下载 PDF：{index}/{len(selected)} · {paper.title}")
                        download_pdf(paper, directory / "pdfs", client.session)
                        export_results(selected, directory, metadata)
                metadata["state"] = "完成（部分详情获取失败，领域筛选可能遗漏论文）" if metadata["detail_failures"] else "完成"
            except (CrawlError, OSError) as exc:
                metadata["state"] = f"中断，结果不完整：{exc}"
            finally:
                # Raw Scholar rows are preserved even if detail retrieval stops early.
                export_results(raw, directory / "source", metadata)
                export_results(selected, directory, metadata)
                st.session_state.result = (selected, directory, metadata)
                status.empty()
                table.empty()

if "result" in st.session_state:
    papers, directory, metadata = st.session_state.result
    st.subheader("论文信息汇总")
    st.write(f"作者：{metadata['author']['name']} · 匹配 {len(papers)} 篇 · 已下载 {sum(p.status == '已下载' for p in papers)} 篇")
    if metadata["state"] == "完成":
        st.success(metadata["state"])
    else:
        st.warning(metadata["state"])
    st.caption(f"本次筛选：{metadata['filters']} · 保存目录：{directory}")
    st.dataframe([{"年份": p.year, "标题": p.title, "作者": p.authors, "发表渠道": p.venue,
                   "引用数": p.citations, "PDF 状态": p.status, "Scholar": p.scholar_url,
                   "备注": p.error} for p in papers], width="stretch",
                 column_config={"Scholar": st.column_config.LinkColumn("Scholar")})
    left, right = st.columns(2)
    left.download_button("导出 CSV 列表", (directory / "papers.csv").read_bytes(), "papers.csv", "text/csv")
    right.download_button("导出 JSON 信息", (directory / "papers.json").read_bytes(), "papers.json", "application/json")
    if st.button("准备完整 ZIP 下载包"):
        archive = directory / "papers.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(directory.rglob("*")):
                if path.is_file() and path.suffix not in (".zip", ".part", ".tmp"):
                    bundle.write(path, path.relative_to(directory))
    if (directory / "papers.zip").exists():
        with (directory / "papers.zip").open("rb") as bundle:
            st.download_button("下载汇总和全部已获取 PDF", bundle, "papers.zip", "application/zip")
    st.subheader("论文 PDF")
    for i, paper in enumerate(papers, 1):
        with st.expander(f"{i}. [{paper.year or '年份未知'}] {paper.title}"):
            st.write(paper.abstract or "未获取到摘要")
            st.link_button("Scholar 论文详情", paper.scholar_url)
            if paper.pdf_file and Path(paper.pdf_file).exists():
                with Path(paper.pdf_file).open("rb") as pdf:
                    st.download_button("下载 PDF", pdf, Path(paper.pdf_file).name, "application/pdf", key=f"pdf_{directory.name}_{paper.id}")
            else:
                st.write(paper.error or paper.status)
