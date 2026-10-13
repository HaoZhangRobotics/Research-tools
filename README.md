# Research-tools

本项目提供一个可视化科研工作台，集中使用论文采集、会议论文整理和科研视频发布工具。每个工具都可单独运行，也可以从统一工作台主动选择。

## 当前功能

- **统一可视化工作台**：从侧边栏选择作者论文采集、会议论文采集或视频发布，无需每次手动挑脚本。
- **作者论文采集**：查找 Google Scholar 作者，按年份和关键词筛选论文，汇总元数据并下载可获取的 PDF。
- **会议论文采集**：从 RSS 等会议目录批量采集论文标题、作者、摘要、BibTeX 和公开 PDF，支持重试失败详情和跳过已下载文件。
- **科研视频发布**：五个平台直接显示为勾选框，默认不选；检查视频与各平台稿件后，统一发布到勾选的平台，并分别显示提交结果。
  - **抖音、B站、小红书、X**：新增本机专用 Chrome 发布适配器，手动登录后自动上传、填写稿件并提交。平台页面流程尚需在用户账号上实测，验证码须由用户完成。
  - **YouTube**：使用官方 API 和 Google OAuth。抖音也保留可选的官方 API 模式。
  - 结果不明时标为“待核查”，不会把点击提交当作成功，也不会自动重复提交。YouTube 默认设为私享。

**Mac 用户可双击项目目录里的 `启动ResearchTools.command`**。第一次启动会自动准备本项目专用的 Python 和依赖，之后双击即可打开工作台。

也可以在终端运行：

```bash
./启动ResearchTools.command
```

首次启动需要联网下载运行环境。完整说明见[工作台说明](tools/README.md)及各工具 README。

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
| [Research Tools 工作台](tools/README.md) | 统一选择和启动下方各工具 | `streamlit run tools/app.py` |
| [科研论文采集器](tools/paper_crawler/README.md) | 按作者 Google Scholar 主页采集论文，支持年份、领域关键词筛选、信息汇总和 PDF 下载 | `streamlit run tools/paper_crawler/app.py` |
| [会议论文采集器](tools/conference_crawler/README.md) | 按 RSS 等会议目录全量采集论文、摘要、BibTeX 和 PDF，支持失败重试与跳过已有文件 | `streamlit run tools/conference_crawler/app.py` |
| [科研视频发布](tools/video_publisher/README.md) | 勾选五个平台，登录或授权后统一发布；浏览器发布流程尚待账号实测 | 见工具说明 |

## Bibliographic catalogs

Repository catalogs contain titles, authors, years, identifiers and source links. Full abstracts, extracted introductions and downloaded PDFs remain in local ignored output directories. After collecting the relevant records, rebuild the metadata catalogs with `python tools/build_metadata_catalog.py`.

- [RSS 2023–2026 catalog](tools/conference_crawler/catalog/README.md)
- [Marco Hutter 2023–2026 catalog](tools/paper_crawler/catalog/README.md)

## 代码仓库

[HaoZhangRobotics/Research-tools](https://github.com/HaoZhangRobotics/Research-tools)
