#!/bin/zsh
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

export UV_INSTALL_DIR="$PROJECT_ROOT/.runtime/bin"
export UV_PYTHON_INSTALL_DIR="$PROJECT_ROOT/.runtime/python"
export UV_CACHE_DIR="$PROJECT_ROOT/.runtime/cache"
export UV_NO_MODIFY_PATH=1
UV_BIN="$UV_INSTALL_DIR/uv"

echo "Research Tools：检查本机运行环境……"
if [[ ! -x "$UV_BIN" ]]; then
  echo "首次启动会下载项目专用 Python 和依赖，请稍候。"
  mkdir -p "$UV_INSTALL_DIR"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

if [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
  if ! "$PROJECT_ROOT/.venv/bin/python" -c 'import platform, sys; assert sys.version_info >= (3, 10); assert platform.machine() == "arm64"; import streamlit, requests, googleapiclient' >/dev/null 2>&1; then
    BACKUP="$PROJECT_ROOT/.venv-old-$(date +%Y%m%d-%H%M%S)"
    echo "发现旧虚拟环境架构不兼容，先保留到 $(basename "$BACKUP")。"
    mv "$PROJECT_ROOT/.venv" "$BACKUP"
  fi
fi

if [[ ! -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
  "$UV_BIN" python install 3.12
  "$UV_BIN" venv --python 3.12 "$PROJECT_ROOT/.venv"
fi

"$UV_BIN" pip install --python "$PROJECT_ROOT/.venv/bin/python" \
  -r tools/paper_crawler/requirements.txt \
  -r tools/conference_crawler/requirements.txt \
  -r tools/video_publisher/requirements-youtube.txt

echo "环境就绪，正在打开 Research Tools……"
exec "$PROJECT_ROOT/.venv/bin/streamlit" run "$PROJECT_ROOT/tools/app.py" \
  --server.showEmailPrompt=false \
  --browser.gatherUsageStats=false
