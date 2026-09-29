# Research-tools

搭建一些有意思、有用的科研工具，让研究工作更高效。

## 项目方向

围绕实际科研需求，逐步开发可独立使用的小工具，例如：

- 文献检索、阅读与整理
- 实验记录、数据处理与结果可视化
- 论文写作与科研工作流自动化

具体工具会随着需求逐步加入。

## 组织约定

每个工具放在独立目录中，并提供自己的 README，说明用途、安装方式、使用示例和依赖。通用组件在确有复用需求时再提取。

工具尽量提供可复现的运行步骤和最小示例，不提交密钥、私有数据或大型实验产物。

## 工具列表

| 工具 | 用途 | 启动方式 |
|---|---|---|
| [科研论文采集器](tools/paper_crawler/README.md) | 按作者 Google Scholar 主页采集论文，支持年份、领域关键词筛选、信息汇总和 PDF 下载 | `streamlit run tools/paper_crawler/app.py` |
| [会议论文采集器](tools/conference_crawler/README.md) | 按 RSS 等会议目录全量采集论文、摘要、BibTeX 和 PDF，支持失败重试与跳过已有文件 | `streamlit run tools/conference_crawler/app.py` |

## Bibliographic catalogs

Repository catalogs contain titles, authors, years, identifiers and source links. Full abstracts, extracted introductions and downloaded PDFs remain in local ignored output directories. After collecting the relevant records, rebuild the metadata catalogs with `python tools/build_metadata_catalog.py`.

- [RSS 2023–2026 catalog](tools/conference_crawler/catalog/README.md)
- [Marco Hutter 2023–2026 catalog](tools/paper_crawler/catalog/README.md)

## 代码仓库

[HaoZhangRobotics/Research-tools](https://github.com/HaoZhangRobotics/Research-tools)
