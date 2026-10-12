# Research Tools 工作台

统一入口把两个论文采集器和科研视频发布器放在一个可视化导航中。启动后可从侧边栏主动选择工具，不用每次再问 Codex。

## 启动

在仓库根目录运行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r tools/paper_crawler/requirements.txt
python -m pip install -r tools/conference_crawler/requirements.txt
python -m pip install -r tools/video_publisher/requirements.txt
streamlit run tools/app.py
```

Python 3.10 或更新版本。也可以继续按各工具 README 中的命令单独启动。

## 视频发布器

使用步骤、OAuth 设置和平台接入范围见 [科研视频发布说明](video_publisher/README.md)。
