#!/bin/bash
# 四级卡片闪卡 — 一键启动（后端 + 前端）
# 用法：在项目根目录运行 bash start.sh
# 停止：bash start.sh stop

cd "$(dirname "$0")"
cd "$(pwd -W 2>/dev/null || pwd)"

ACTION=${1:-start}

stop_all() {
  echo "🛑 停止所有服务..."
  taskkill //F //IM python.exe 2>/dev/null && echo "  后端已停" || echo "  后端未运行"
  # 只停前端的 next dev，不影响其他 node
  for pid in $(netstat -ano 2>/dev/null | grep ":3000" | grep LISTENING | awk '{print $5}' | sort -u); do
    taskkill //F //PID $pid 2>/dev/null && echo "  前端(pid $pid)已停"
  done
}

if [ "$ACTION" = "stop" ]; then
  stop_all
  exit 0
fi

# 启动后端
echo "🚀 启动后端 (localhost:8000)..."
cd backend
nohup python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > /tmp/cet4_backend.log 2>&1 &
BACKEND_PID=$!
cd ..

# 启动前端
echo "🎨 启动前端 (localhost:3000)..."
cd frontend
nohup npm run dev > /tmp/cet4_frontend.log 2>&1 &
FRONTEND_PID=$!
cd ..

echo ""
echo "⏳ 等待启动（后端约8秒加载词库，前端约5秒）..."
sleep 12

# 检查状态
echo ""
echo "=== 状态检查 ==="
if netstat -ano 2>/dev/null | grep -q ":8000.*LISTENING"; then
  echo "✅ 后端运行中 (http://localhost:8000)"
else
  echo "❌ 后端启动失败，日志："
  tail -10 /tmp/cet4_backend.log
fi
if netstat -ano 2>/dev/null | grep -q ":3000.*LISTENING"; then
  echo "✅ 前端运行中 (http://localhost:3000)"
else
  echo "❌ 前端启动失败，日志："
  tail -10 /tmp/cet4_frontend.log
fi
echo ""
echo "🌐 打开浏览器访问：http://localhost:3000"
echo "📝 日志：后端 /tmp/cet4_backend.log，前端 /tmp/cet4_frontend.log"
echo "🛑 停止：bash start.sh stop"
