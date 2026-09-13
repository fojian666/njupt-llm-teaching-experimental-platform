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
#   ./start.sh stop       停掉本项目的后端/前端进程
#   ./start.sh status     看两边的运行状态
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

# 注意末尾的 || true：端口空闲时 lsof 退出码非 0，在 set -e + pipefail 下会直接把脚本带走
port_pid()  { lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null | head -1 || true; }
port_busy() { [ -n "$(port_pid "$1")" ]; }
cmd_of()    { ps -o command= -p "$1" 2>/dev/null || true; }

# 端口归属判断：优先看命令行特征；如果读不到（进程属于别的终端会话，ps 对本会话不可见），
# 就退化成"服务能不能答话"——能答我们自己的接口/页面，就认定是自己人。
back_responds()  { curl -s -m 2 "http://127.0.0.1:$BACK_PORT/api/ping" 2>/dev/null | grep -q '"pong"'; }
front_responds() { curl -s -m 2 "http://127.0.0.1:$FRONT_PORT/" 2>/dev/null | grep -q '物联网学科大模型教学实验平台'; }

is_our_backend() {
  case "$(cmd_of "$1")" in *"manage.py runserver"*"$BACK_PORT"*) return 0 ;; esac
  back_responds
}
is_our_front() {
  case "$(cmd_of "$1")" in *vite*"$FRONT_PORT"*) return 0 ;; esac
  front_responds
}

# ---------- 环境检查 ----------
BACK_ALREADY=0
FRONT_ALREADY=0

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
    local pid; pid="$(port_pid "$BACK_PORT")"
    if is_our_backend "$pid"; then
      # 复用已有实例，而不是直接退出 —— 否则前端也跟着起不来，整站看起来像坏了
      warn "后端已在运行（PID $pid），跳过启动，直接复用
  注意：复用的是旧进程，改了 backend/.env 不会生效。
  要用最新配置重启：./start.sh stop && ./start.sh"
      BACK_ALREADY=1
    else
      fail "端口 $BACK_PORT 被别的进程占用：
  PID $pid  $(cmd_of "$pid" | cut -c1-100)
  释放它：kill $pid"
    fi
  fi
}

check_front() {
  [ -d "$FRONT_DIR" ] || fail "找不到 frontend 目录：$FRONT_DIR"
  if [ ! -d "$FRONT_DIR/node_modules" ]; then
    fail "前端依赖未安装。
  先执行：cd frontend && npm install --registry=https://registry.npmmirror.com"
  fi
  if port_busy "$FRONT_PORT"; then
    local pid; pid="$(port_pid "$FRONT_PORT")"
    if is_our_front "$pid"; then
      warn "前端已在运行（PID $pid），跳过启动，直接复用"
      FRONT_ALREADY=1
    else
      fail "端口 $FRONT_PORT 被别的进程占用：
  PID $pid  $(cmd_of "$pid" | cut -c1-100)
  释放它：kill $pid"
    fi
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

# ---------- stop / status ----------
stop_one() { # $1=端口  $2=该端口的归属判断函数名
  local pid; pid="$(port_pid "$1")"
  if [ -z "$pid" ]; then
    info "端口 $1 没有进程"
    return 0
  fi
  if "$2" "$pid"; then
    kill "$pid" 2>/dev/null || true
    info "已停止 $1 上的进程（PID $pid）"
  else
    warn "端口 $1 被非本项目进程占用（PID $pid），没动它"
  fi
}

show_status() {
  local spec port rest label fn pid
  for spec in "$BACK_PORT:后端:is_our_backend" "$FRONT_PORT:前端:is_our_front"; do
    port="${spec%%:*}"; rest="${spec#*:}"; label="${rest%%:*}"; fn="${rest##*:}"
    pid="$(port_pid "$port")"
    if [ -z "$pid" ]; then
      printf '  %s(%s)  未运行\n' "$label" "$port"
    elif "$fn" "$pid"; then
      printf '  %s(%s)  运行中  PID %s\n' "$label" "$port" "$pid"
    else
      printf '  %s(%s)  被其他进程占用  PID %s\n' "$label" "$port" "$pid"
    fi
  done
}

# ---------- 主流程 ----------
echo "──────────────────────────────────────────────"
echo "  南京邮电大学物联网学科大模型教学实验平台"
echo "──────────────────────────────────────────────"

case "$MODE" in
  stop)
    stop_one "$FRONT_PORT" is_our_front
    stop_one "$BACK_PORT" is_our_backend
    show_status
    exit 0
    ;;
  status)
    show_status
    exit 0
    ;;
  back)
    check_back
    [ "$BACK_ALREADY" = "1" ] || start_back
    ;;
  front)
    check_front
    [ "$FRONT_ALREADY" = "1" ] || start_front
    ;;
  all)
    check_back; check_front
    [ "$BACK_ALREADY" = "1" ] || start_back
    if [ "$FRONT_ALREADY" = "0" ]; then
      sleep 2
      start_front
    fi
    echo
    echo "  后端  http://127.0.0.1:$BACK_PORT      （API 文档 /api/docs）"
    echo "  前端  http://127.0.0.1:$FRONT_PORT      （登录 admin / admin123）"
    echo "  按 Ctrl+C 停止全部服务（本就有、被复用的进程不会被停）"
    echo
    ;;
  *)
    fail "未知参数：$MODE（可选：all / back / front / stop / status）"
    ;;
esac

wait
