#!/bin/bash

# VoxCast macOS one-click launcher.
# Double-click this file in Finder. It never uses sudo and keeps all Python
# packages inside this project folder.

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

VENV_DIR="$SCRIPT_DIR/.voxcast-venv"
VENV_PYTHON="$VENV_DIR/bin/python"
PORT="${VOXCAST_PORT:-8000}"
APP_URL="http://127.0.0.1:$PORT"

pause_before_exit() {
  if [ -t 0 ]; then
    printf "\n按回车键关闭这个窗口…"
    read -r _unused
  fi
}

fail() {
  printf "\n❌ %s\n" "$1"
  printf "如果仍然无法解决，请把这个窗口最后 20 行截图发给开发组。\n"
  pause_before_exit
  exit 1
}

app_is_running() {
  if ! command -v curl >/dev/null 2>&1; then
    return 1
  fi
  curl -fsS --max-time 1 "$APP_URL/api/health" 2>/dev/null |
    grep -Eq '"status"[[:space:]]*:[[:space:]]*"ok"'
}

open_app() {
  if command -v open >/dev/null 2>&1; then
    open "$APP_URL" >/dev/null 2>&1 || true
  fi
}

printf "\n🎧 声场 VoxCast · Mac 一键启动\n"
printf "项目目录：%s\n" "$SCRIPT_DIR"

case "$PORT" in
  ""|*[!0-9]*)
    fail "端口必须是 1–65535 之间的数字，当前值为：$PORT"
    ;;
esac
if [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
  fail "端口必须是 1–65535 之间的数字，当前值为：$PORT"
fi

PYTHON_BIN=""
if [ -n "${VOXCAST_QUICKSTART_PYTHON:-}" ]; then
  if [ ! -x "$VOXCAST_QUICKSTART_PYTHON" ]; then
    fail "指定的 Python 不可执行：$VOXCAST_QUICKSTART_PYTHON"
  fi
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

if [ -z "$PYTHON_BIN" ]; then
  fail "没有找到 Python 3.10 或更高版本。请先从 python.org 安装 Python 3。"
fi
if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
  python_version="$("$PYTHON_BIN" --version 2>&1 || true)"
  fail "需要 Python 3.10 或更高版本，当前是：$python_version"
fi

printf "Python：%s\n" "$("$PYTHON_BIN" --version 2>&1)"

if [ "${VOXCAST_QUICKSTART_DRY_RUN:-0}" = "1" ]; then
  printf "虚拟环境：%s\n" "$VENV_DIR"
  printf "网址：%s\n" "$APP_URL"
  printf "VOXCAST_QUICKSTART_OK=1\n"
  exit 0
fi

if [ "$(uname -s)" != "Darwin" ]; then
  fail "这个双击启动器仅支持 macOS；其他系统请运行 python3 -m audiobook_app。"
fi

if app_is_running; then
  printf "\n✅ 声场已经在运行，正在打开浏览器：%s\n" "$APP_URL"
  open_app
  exit 0
fi

if [ ! -x "$VENV_PYTHON" ]; then
  printf "\n[1/3] 第一次运行：正在创建独立环境…\n"
  if ! "$PYTHON_BIN" -m venv "$VENV_DIR"; then
    fail "无法创建独立环境。请确认 Python 安装完整后重试。"
  fi
else
  if ! "$VENV_PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
    fail "现有 .voxcast-venv 使用了过旧的 Python；请将该文件夹改名后重新双击。"
  fi
  printf "\n[1/3] 独立环境已经准备好。\n"
fi

if "$VENV_PYTHON" -c 'import edge_tts, miniaudio' >/dev/null 2>&1; then
  printf "[2/3] 免费 Neural 中文声线已经安装。\n"
else
  printf "[2/3] 正在安装免费 Neural 中文声线（第一次需要联网）…\n"
  if ! "$VENV_PYTHON" -m pip install --disable-pip-version-check -e ".[neural]"; then
    printf "\n⚠️ Neural 声线安装失败，可能是暂时断网。\n"
    printf "仍将启动基础版；下次联网后再次双击会自动重试。\n"
  fi
fi

if ! "$VENV_PYTHON" -c 'import audiobook_app' >/dev/null 2>&1; then
  fail "项目文件不完整，无法导入 audiobook_app。请重新下载仓库。"
fi

printf "[3/3] 正在启动网页：%s\n" "$APP_URL"
printf "关闭程序时，在这个窗口按 Control + C。\n\n"

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
