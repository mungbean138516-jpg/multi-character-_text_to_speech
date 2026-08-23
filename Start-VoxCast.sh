#!/usr/bin/env bash

# VoxCast Linux quick launcher. It never uses sudo and installs everything
# inside the repository's .voxcast-venv directory.

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

VENV_DIR="$SCRIPT_DIR/.voxcast-venv"
VENV_PYTHON="$VENV_DIR/bin/python"
PORT="${VOXCAST_PORT:-8000}"
APP_URL="http://127.0.0.1:$PORT"

fail() {
  printf "\n❌ %s\n" "$1"
  exit 1
}

app_is_running() {
  command -v curl >/dev/null 2>&1 &&
    curl -fsS --max-time 1 "$APP_URL/api/health" 2>/dev/null |
      grep -Eq '"status"[[:space:]]*:[[:space:]]*"ok"'
}

open_app() {
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$APP_URL" >/dev/null 2>&1 || true
  fi
}

printf "\n🎧 声场 VoxCast · Linux 快速启动\n"

case "$PORT" in
  ""|*[!0-9]*) fail "端口必须是 1–65535 之间的数字，当前值为：$PORT" ;;
esac
if [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
  fail "端口必须是 1–65535 之间的数字，当前值为：$PORT"
fi

PYTHON_BIN=""
if [ -n "${VOXCAST_QUICKSTART_PYTHON:-}" ]; then
  PYTHON_BIN="$VOXCAST_QUICKSTART_PYTHON"
else
  for command_name in python3.13 python3.12 python3.11 python3.10 python3; do
    candidate="$(command -v "$command_name" 2>/dev/null || true)"
    if [ -n "$candidate" ] &&
      "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
      PYTHON_BIN="$candidate"
      break
    fi
  done
fi

if [ -z "$PYTHON_BIN" ] || [ ! -x "$PYTHON_BIN" ]; then
  fail "没有找到 Python 3.10 或更高版本。"
fi

if [ "${VOXCAST_QUICKSTART_DRY_RUN:-0}" = "1" ]; then
  printf "Python：%s\n" "$PYTHON_BIN"
  printf "虚拟环境：%s\n" "$VENV_DIR"
  printf "网址：%s\n" "$APP_URL"
  printf "VOXCAST_QUICKSTART_OK=1\n"
  exit 0
fi

if app_is_running; then
  printf "\n✅ 声场已经在运行：%s\n" "$APP_URL"
  open_app
  exit 0
fi

if [ ! -x "$VENV_PYTHON" ]; then
  printf "[1/3] 正在创建项目独立环境…\n"
  "$PYTHON_BIN" -m venv "$VENV_DIR" || fail "无法创建虚拟环境。"
else
  printf "[1/3] 项目独立环境已准备好。\n"
fi

if "$VENV_PYTHON" -c 'import audiobook_app, edge_tts, miniaudio' >/dev/null 2>&1; then
  printf "[2/3] 项目与免费 Neural 声线已安装。\n"
else
  printf "[2/3] 正在安装项目与免费 Neural 声线…\n"
  if ! "$VENV_PYTHON" -m pip install --disable-pip-version-check -e ".[neural]"; then
    printf "⚠️ Neural 依赖安装失败，将尝试启动基础版。\n"
  fi
fi

"$VENV_PYTHON" -c 'import audiobook_app' >/dev/null 2>&1 ||
  fail "项目依赖不完整，无法启动 audiobook_app。"

printf "[3/3] 正在启动：%s\n" "$APP_URL"
printf "关闭程序时，在当前窗口按 Control + C。\n\n"

(
  attempt=0
  while [ "$attempt" -lt 20 ]; do
    if app_is_running; then
      open_app
      exit 0
    fi
    attempt=$((attempt + 1))
    sleep 1
  done
) &
opener_pid=$!

"$VENV_PYTHON" -m audiobook_app serve --port "$PORT"
server_status=$?
kill "$opener_pid" >/dev/null 2>&1 || true
wait "$opener_pid" 2>/dev/null || true
if [ "$server_status" -ne 0 ] && [ "$server_status" -ne 130 ]; then
  fail "网页服务启动失败，退出码为 $server_status。"
fi
