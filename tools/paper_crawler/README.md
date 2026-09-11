# 科研论文采集器

输入作者姓名、Google Scholar 主页或作者 ID，先整理论文信息，再下载可获取的 PDF。中文网页界面上方显示论文汇总列表，下方逐篇提供摘要、原始链接和 PDF 下载。

## 启动

需要 Python 3.10+，在仓库根目录执行：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r tools/paper_crawler/requirements.txt
streamlit run tools/paper_crawler/app.py
```

打开终端显示的本地地址，通常是 `http://localhost:8501`。

## 使用

1. 输入作者姓名，建议带学校；从候选列表选择正确作者。搜索展示 Scholar 第一页候选，找不到时请直接提供主页。
2. 也可输入 `https://scholar.google.com/citations?user=AUTHOR_ID`；裸 ID 需勾选“输入的是作者 ID”。
3. 默认“全爬”，遍历主页全部可见论文。取消勾选后可以设置起止年份（含边界，0 表示不限）和领域关键词。
4. 多个关键词用中英文逗号分隔，任意一个出现在标题、摘要或发表渠道即匹配。不做语义分类、不自动翻译；摘要缺失时只能依据现有字段。限定年份时排除未知年份论文。
5. 开始采集；论文汇总先保存，随后下载 PDF。可下载 CSV、JSON、单篇 PDF 或完整 ZIP。

## 输出

每次运行使用独立目录 `tools/paper_crawler/output/<作者ID>_<时间>_<随机后缀>/`：

```text
README.md       # 上方论文汇总表，下方 PDF 文件链接
index.html      # 可直接用浏览器打开的结果页：上方列表，下方 PDF
papers.csv      # 可在 Excel 中打开
papers.json     # 作者、筛选参数、完成状态、论文元数据和下载结果
pdfs/           # 年份_标题_稳定标识.pdf
source/         # 原始 Scholar 列表及已获取详情，中断时也保留
papers.zip      # 点击“准备完整 ZIP 下载包”后生成
```

元数据包括标题、年份、作者、发表渠道、引用数、摘要、Scholar 链接、来源链接、PDF 地址、文件名和错误原因。按 Scholar 条目标识去重，不自动合并作者主页中的不同版本。PDF 路径相对于各自的汇总文件目录。

## 数据来源与边界

- 直接读取 Google Scholar 作者主页和论文详情，默认请求间隔至少两秒。参考 [Google Scholar 帮助](https://scholar.google.com/intl/us/scholar/help.html)。页面结构变化可能需要更新解析器。
- Google Scholar 不保证允许自动访问；遇到 403、429 或验证码立即停止并标记结果不完整，不自动绕过验证。运行环境需要能够访问 Scholar 和论文网站。
- PDF 来源为 Scholar 全文链接、论文来源页的 `citation_pdf_url` / `wkhealth_pdf_url` 元数据，以及 arXiv 标准 PDF 地址。不保证所有论文有可下载全文，不处理付费墙或机构登录。
- 下载检查 `%PDF-` 文件头，单文件上限 80 MB，最多尝试六个链接；失败保留论文信息和原因。现有同名 PDF 可复用，但新采集会创建新目录；暂不提供跨任务断点续采。
- 本工具供本地个人使用，未实现多用户鉴权。大量 PDF 的 ZIP 导出可能占用较多内存。

## 测试

```bash
python -m unittest discover -s tools/paper_crawler/tests -v
```

测试用本地模拟响应验证分页、筛选、阻断识别、PDF 校验、下载大小限制和导出，不依赖 Scholar 在线可用性。
