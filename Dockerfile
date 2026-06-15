# === 阶段1：构建前端静态文件 ===
FROM node:20-alpine AS frontend-builder

WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci || npm install
COPY frontend/ ./
# 静态导出（output: export），产物在 /build/out
RUN npm run build

# === 阶段2：Python 后端 + 前端静态 ===
FROM python:3.11-slim

WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 后端代码
COPY backend/app/ ./app/

# 前端静态文件 → 后端 static/ 目录（main.py 的 STATIC_DIR 指向 ../static）
COPY --from=frontend-builder /build/out ./static/

# 持久化目录（SQLite 存这里，容器重启不丢）
RUN mkdir -p /data
VOLUME ["/data"]

# HF Spaces 要 7860，Sealos/其他用 8000
ENV PORT=8000
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# 启动
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
