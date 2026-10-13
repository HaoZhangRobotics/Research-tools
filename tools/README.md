# Research Tools 工作台

统一入口把两个论文采集器和科研视频发布器放在一个可视化导航中。启动后可从侧边栏主动选择工具，不用每次再问 Codex。

## 启动

Mac 上直接双击仓库根目录的 `启动ResearchTools.command`，首次会自动准备 Python 和项目依赖。或在终端运行：

```bash
./启动ResearchTools.command
```

启动器使用项目内独立的 arm64 Python 环境，不依赖系统 Python 或 Anaconda。首次运行需联网下载环境；旧的架构不匹配 `.venv` 会保留为备份。也可以手动安装 Python 3.10 或更新版本，再运行 `streamlit run tools/app.py`。

重复双击时，启动器会打开本项目已经运行的工作台。新启动时会在 8501–8510 中选择空闲端口，等服务就绪后自动打开浏览器；实际地址以启动窗口为准。关闭新启动工作台的终端窗口会停止该服务。

## 视频发布器

使用步骤、OAuth 设置和平台接入范围见 [科研视频发布说明](video_publisher/README.md)。
