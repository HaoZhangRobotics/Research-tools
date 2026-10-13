#!/bin/zsh
set -euo pipefail
setopt NO_BG_NICE

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

APP_PORT=""
for CANDIDATE_PORT in {8501..8510}; do
  LISTENER_PID="$(lsof -nP -iTCP:"$CANDIDATE_PORT" -sTCP:LISTEN -t 2>/dev/null | head -n 1 || true)"
  if [[ -z "$LISTENER_PID" ]]; then
    [[ -n "$APP_PORT" ]] || APP_PORT="$CANDIDATE_PORT"
    continue
  fi
  LISTENER_COMMAND="$(ps -p "$LISTENER_PID" -o command= 2>/dev/null || true)"
  if [[ "$LISTENER_COMMAND" == *"$PROJECT_ROOT/tools/app.py"* ]]; then
    APP_URL="http://localhost:$CANDIDATE_PORT"
    echo "Research Tools 已在运行，正在打开 $APP_URL"
    open "$APP_URL" || echo "请在浏览器打开 $APP_URL"
    exit 0
  fi
done
if [[ -z "$APP_PORT" ]]; then
  echo "8501–8510 端口均已被占用，请关闭一个旧工作台后重试。"
  exit 1
fi

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
"$PROJECT_ROOT/.venv/bin/streamlit" run "$PROJECT_ROOT/tools/app.py" \
  --server.port="$APP_PORT" \
  --server.headless=true \
  --server.showEmailPrompt=false \
  --browser.gatherUsageStats=false &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT INT TERM
APP_URL="http://localhost:$APP_PORT"
for ATTEMPT in {1..100}; do
  if curl -fsS "$APP_URL/_stcore/health" >/dev/null 2>&1; then
    open "$APP_URL" || echo "请在浏览器打开 $APP_URL"
    wait "$SERVER_PID"
    exit 0
  fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "工作台启动失败，请查看上方错误信息。"
    exit 1
  fi
  sleep 0.1
done
echo "工作台还在启动，请在浏览器打开 $APP_URL"
wait "$SERVER_PID"
