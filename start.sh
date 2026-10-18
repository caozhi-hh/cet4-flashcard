#!/bin/bash
# 腰子背单词（四级词汇闪卡）— 一键启动 / 停止
#
# 用法（在项目根目录，用 Git Bash 执行）：
#   注意：Windows 自带 PATH 里的 bash 是 WSL，本脚本在 WSL 下跑不通（路径与 taskkill 行为不同）。
#   请用 Git Bash："/c/Program Files/Git/bin/bash.exe" start.sh
#   不想用 bash 的话，直接一条 PowerShell 命令即可（等价于本脚本的默认行为）：
#     cd backend; python -m uvicorn app.main:app --port 8000
#   bash start.sh              启动后端；前端页面由后端同源托管 → http://localhost:8000
#   bash start.sh dev          额外启动前端开发服务器（改前端代码时才需要）→ http://localhost:3000
#   bash start.sh stop         停止本项目占用的端口（只停本项目的进程，不动其他 python/node）
#   HOST=0.0.0.0 bash start.sh 监听所有网卡，手机连同一 WiFi 可直接访问
#
# 说明：合并部署下前端已构建进 backend/static/ 并由后端托管，所以日常只需启动后端。

cd "$(dirname "$0")"
cd "$(pwd -W 2>/dev/null || pwd)" || exit 1

ACTION=${1:-start}
PORT=${PORT:-8000}
HOST=${HOST:-127.0.0.1}
DEV_PORT=3000
LOG_DIR="${TMPDIR:-/tmp}"

# 只停"确实监听了指定端口、且进程名匹配"的进程，避免误杀机器上其他项目的进程。
# 旧实现用 taskkill //F //IM python.exe 会杀掉全机所有 python，这里已改掉。
stop_port() {
  local port=$1 expect=$2
  local pids name pid
  pids=$(netstat -ano 2>/dev/null | grep -E "[:.]${port}[[:space:]]" | grep LISTENING | awk '{print $NF}' | sort -u)
  if [ -z "$pids" ]; then
    echo "  端口 ${port} 未被占用"
    return
  fi
  for pid in $pids; do
    name=$(tasklist //FI "PID eq ${pid}" //FO CSV //NH 2>/dev/null | head -1 | awk -F'","' '{print $1}' | tr -d '"')
    if [ "$name" = "$expect" ]; then
      taskkill //F //PID "${pid}" >/dev/null 2>&1 && echo "  已停 ${expect} (pid ${pid}, 端口 ${port})"
    elif [ -z "$name" ]; then
      # tasklist 不可用/被拒时取不到进程名。为安全起见不盲杀，但要明确告知，避免"stop 什么都没停"。
      echo "  ⚠️  端口 ${port} 上有 pid ${pid}，但无法识别进程名（tasklist 不可用），未终止"
      echo "     确认是本项目后可手动执行：taskkill /F /PID ${pid}"
    else
      echo "  跳过 pid ${pid}（${name}）—— 不是本项目的 ${expect}，未终止"
    fi
  done
}

if [ "$ACTION" = "stop" ]; then
  echo "🛑 停止服务..."
  stop_port "$PORT" "python.exe"
  stop_port "$DEV_PORT" "node.exe"
  exit 0
fi

# === 启动后端（同时托管已构建的前端页面）===
echo "🚀 启动后端 (http://${HOST}:${PORT})..."
cd backend || exit 1
nohup python -m uvicorn app.main:app --host "$HOST" --port "$PORT" > "${LOG_DIR}/cet4_backend.log" 2>&1 &
cd ..

if [ "$ACTION" = "dev" ]; then
  echo "🎨 启动前端开发服务器 (http://localhost:${DEV_PORT})..."
  cd frontend || exit 1
  nohup npm run dev > "${LOG_DIR}/cet4_frontend.log" 2>&1 &
  cd ..
  sleep 12
else
  sleep 8
fi

# === 状态检查 ===
echo ""
echo "=== 状态检查 ==="
if netstat -ano 2>/dev/null | grep -E "[:.]${PORT}[[:space:]]" | grep -q LISTENING; then
  echo "✅ 后端运行中 (http://localhost:${PORT})"
  if [ "$HOST" = "0.0.0.0" ]; then
    echo "   📱 手机访问：http://<本机局域网IP>:${PORT}（用 ipconfig 看 IPv4 地址）"
  else
    echo "   ℹ️  当前仅本机可访问；手机要用请执行：HOST=0.0.0.0 bash start.sh"
  fi
else
  echo "❌ 后端启动失败，日志末尾："
  tail -15 "${LOG_DIR}/cet4_backend.log"
fi

if [ "$ACTION" = "dev" ]; then
  if netstat -ano 2>/dev/null | grep -E "[:.]${DEV_PORT}[[:space:]]" | grep -q LISTENING; then
    echo "✅ 前端开发服务器运行中 (http://localhost:${DEV_PORT})"
  else
    echo "❌ 前端启动失败，日志末尾："
    tail -15 "${LOG_DIR}/cet4_frontend.log"
  fi
fi

echo ""
echo "🌐 打开浏览器访问：http://localhost:${PORT}"
echo "📝 日志：${LOG_DIR}/cet4_backend.log"
echo "🛑 停止：bash start.sh stop"