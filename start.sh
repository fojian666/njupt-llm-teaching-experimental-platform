#!/usr/bin/env bash
#
# 一键启动前后端（开发模式）
#   后端 Django + Ninja  -> http://127.0.0.1:8000  （/api/docs 可看 OpenAPI）
#   前端 Vite            -> http://127.0.0.1:5173  （/api 已代理到后端）
#
# 用法：
#   ./start.sh            同时启动前后端
#   ./start.sh back       只启动后端
#   ./start.sh front      只启动前端
#
# 停止：在终端按 Ctrl+C，两个进程会一起退出。
# 日志：.logs/backend.log、.logs/frontend.log（同时彩色输出到当前终端）
# 热重载：默认关闭；改后端代码想自动重启用 RELOAD=1 ./start.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACK_DIR="$ROOT/backend"
FRONT_DIR="$ROOT/frontend"
BACK_PORT=8000
FRONT_PORT=5173
LOG_DIR="$ROOT/.logs"

MODE="${1:-all}"

# 后端是否开启代码热重载：默认关闭（单进程，Ctrl+C 停得更干净）。
# 需要边改 .py 边自动重启时：RELOAD=1 ./start.sh
BACK_EXTRA="--noreload"
[ "${RELOAD:-0}" = "1" ] && BACK_EXTRA=""

# ---------- 工具函数 ----------
info()  { printf '\033[36m[启动]\033[0m %s\n' "$1"; }
warn()  { printf '\033[33m[警告]\033[0m %s\n' "$1"; }
fail()  { printf '\033[31m[错误]\033[0m %s\n' "$1"; exit 1; }

port_busy() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

# ---------- 环境检查 ----------
check_back() {
  [ -d "$BACK_DIR" ] || fail "找不到 backend 目录：$BACK_DIR"
  if [ ! -x "$BACK_DIR/.venv/bin/python" ]; then
    fail "缺少虚拟环境 backend/.venv
  先执行：cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  fi
  if [ ! -f "$BACK_DIR/.env" ]; then
    if [ -f "$BACK_DIR/.env.example" ]; then
      warn "backend/.env 不存在，已从 .env.example 复制一份，请补上模型 API Key"
      cp "$BACK_DIR/.env.example" "$BACK_DIR/.env"
    else
      fail "缺少 backend/.env（模型 API Key 配置），请参考 README 补齐后重试"
    fi
  fi
  if port_busy "$BACK_PORT"; then
    fail "端口 $BACK_PORT 已被占用（可能后端已在运行）。先停止它，或改用 front 模式。"
  fi
}

check_front() {
  [ -d "$FRONT_DIR" ] || fail "找不到 frontend 目录：$FRONT_DIR"
  if [ ! -d "$FRONT_DIR/node_modules" ]; then
    fail "前端依赖未安装。
  先执行：cd frontend && npm install --registry=https://registry.npmmirror.com"
  fi
  if port_busy "$FRONT_PORT"; then
    fail "端口 $FRONT_PORT 已被占用（可能前端已在运行）。先停止它，或改用 back 模式。"
  fi
}

# ---------- 启动 ----------
# 说明：用进程替换（> >(awk | tee)）承接日志，这样后台任务的 $! 就是
# 真正的服务进程（Django / vite），而不是管道末尾的 tee，Ctrl+C 才能干净退出。
PIDS=()
cleanup() {
  echo
  info "正在停止服务..."
  for pid in ${PIDS[@]:-}; do
    kill "$pid" 2>/dev/null || true
  done
  sleep 1
  for pid in ${PIDS[@]:-}; do
    kill -9 "$pid" 2>/dev/null || true
  done
  info "已全部停止"
}
trap cleanup INT TERM

mkdir -p "$LOG_DIR"

start_back() {
  info "后端启动中 -> http://127.0.0.1:$BACK_PORT"
  # -u 关闭 python 输出缓冲：stdout 接到管道后默认块缓冲，启动横幅会卡在缓冲区里看不到
  ( cd "$BACK_DIR" && exec .venv/bin/python -u manage.py runserver "127.0.0.1:$BACK_PORT" ${BACK_EXTRA:-} ) \
    > >(awk '{ printf "\033[36m[后端]\033[0m %s\n", $0; fflush() }' | tee -a "$LOG_DIR/backend.log") 2>&1 &
  PIDS+=("$!")
}

start_front() {
  info "前端启动中 -> http://127.0.0.1:$FRONT_PORT"
  ( cd "$FRONT_DIR" && exec ./node_modules/.bin/vite ) \
    > >(awk '{ printf "\033[35m[前端]\033[0m %s\n", $0; fflush() }' | tee -a "$LOG_DIR/frontend.log") 2>&1 &
  PIDS+=("$!")
}

# ---------- 主流程 ----------
echo "──────────────────────────────────────────────"
echo "  南京邮电大学物联网学科大模型教学实验平台"
echo "──────────────────────────────────────────────"

case "$MODE" in
  back)
    check_back; start_back
    ;;
  front)
    check_front; start_front
    ;;
  all)
    check_back; check_front
    start_back; sleep 2; start_front
    echo
    echo "  后端  http://127.0.0.1:$BACK_PORT      （API 文档 /api/docs）"
    echo "  前端  http://127.0.0.1:$FRONT_PORT      （登录 admin / admin123）"
    echo "  按 Ctrl+C 停止全部服务"
    echo
    ;;
  *)
    fail "未知参数：$MODE（可选：all / back / front）"
    ;;
esac

wait
