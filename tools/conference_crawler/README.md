# 会议论文采集器

按会议论文目录全量采集标题、作者、年份、会议、摘要、DOI、BibTeX 和公开 PDF。提供中文 Streamlit 界面和命令行。

RSS 指 **Robotics: Science and Systems** 会议，本工具不是 RSS/Atom 订阅解析器。内置适配 roboticsproceedings.org 各届目录，默认示例为 [RSS 2026 / XXII](https://www.roboticsproceedings.org/rss22/index.html)。

届次映射：`rss19` = 2023、`rss20` = 2024、`rss21` = 2025、`rss22` = 2026；RSS 2022 是 `rss18`，需要单独运行。

## 安装与启动

Python 3.10+，在仓库根目录执行：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r tools/conference_crawler/requirements.txt
streamlit run tools/conference_crawler/app.py
```

输入会议目录地址，点击“全量采集”。若同时运行 Scholar 工具，可添加 `--server.port 8502`。

## 命令行

```bash
# 下载本届全部论文；再次执行同一命令重试失败项，跳过已完成详情和已有完整 PDF
python tools/conference_crawler/crawler.py \
  https://www.roboticsproceedings.org/rss22/index.html \
  --output tools/conference_crawler/output/rss22

# 只采集论文信息、摘要与引用
python tools/conference_crawler/crawler.py --no-pdf

# 其他会议：选择目录内指向论文详情或 PDF 的链接
python tools/conference_crawler/crawler.py https://example.org/proceedings/ \
  --selector 'a.paper-link' --output tools/conference_crawler/output/example
```

默认最多 4 路并发下载（`--workers 1` 可切换串行），所有线程共享限速器。默认请求间隔 1 秒，`--delay` 可调整（最低 0.2 秒）。RSS 仅提取当前届 `p数字.html` 链接，自动去重，不跟随往届菜单。其他会议使用指定 CSS 选择器提取当前目录中的链接，并读取详情页标准 `citation_*` 元数据、摘要、内嵌 BibTeX 和 PDF 链接；不保证兼容所有会议站点。暂不自动翻页或执行 JavaScript，分页目录需分别采集。

## 输出与续采

```text
papers.json     # 全部字段、完整性标记、详情与 PDF 独立状态、错误原因
papers.csv      # UTF-8 BOM 编码的论文列表
papers.bib      # 详情页提供的 BibTeX 原文
index.html      # 本地汇总页，含摘要、原始链接及本地 PDF 链接
pdfs/           # 按论文 URL 稳定标识命名，避免标题文件名过长
source/         # 原始目录页及已读取详情页
papers.zip      # 在网页界面点击生成后创建
```

未指定输出目录时，以目录 URL 自动生成固定目录。相同目录重跑会重新读取目录、重试失败详情与 PDF，并校验已有 PDF 后跳过；成功详情使用缓存，如需重新抓取已成功的元数据，请使用新目录。JSON 中 `pdf_file` 为相对路径，整个目录可移动。

每篇完成即保存进度；遇到 403/429 停止任务，连接/响应阶段的网络或 5xx 错误最多尝试三次（传输途中断流保存失败状态，重跑时重试），普通单篇错误保留记录并继续。PDF 流式下载至 `.part`，检查文件头、尾部 EOF、响应长度和 200 MB 上限，完成后原子替换。中断后重跑会重新下载未完成的单个文件，不支持单文件字节续传。CLI 完全成功退出码为 0，缺失或中断为 1。

本地个人工具，无多用户鉴权；仅下载页面公开提供的资源。ZIP 使用无压缩打包，超过 200 MB 时显示本地路径，避免网页加载大量文件占用内存。输出默认被 Git 忽略。

## 测试

```bash
python -m unittest discover -s tools/conference_crawler/tests -v
```

离线测试覆盖目录去重与届次限制、元数据提取、其他会议选择器、PDF 内容和大小校验、续采、导出及限流保留进度。
