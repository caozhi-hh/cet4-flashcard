# 四级词汇闪卡

AI 驱动的大学英语四级词汇学习工具。

## 功能
- 📖 每天学习 20 个新词，闪卡翻转记忆
- 💡 AI 生成记忆口诀（拆分联想 + 谐音 + 情境）
- 🔄 间隔重复复习，不认识的词反复出现
- ✏️ 每日测验（选择题 + 填空题）
- 📊 学习进度统计

## 技术栈
- **后端**: FastAPI + SQLite + 智谱 GLM（OpenAI 兼容接口）
- **前端**: Next.js（静态导出）+ Tailwind CSS
- **部署**: 合并部署——FastAPI 一个进程同时托管前端静态页 + API（见 `部署文档_SeaLOS.md`）
- **本地使用**: 直接启动后端即可，前端页面由后端同源托管

## 本地使用（日常背单词，只要一条命令）

```bash
cd backend
python -m uvicorn app.main:app --port 8000
```
然后浏览器打开 http://localhost:8000

- 手机想用（同一 WiFi）：把 `--host 0.0.0.0` 加上，再用 `http://<电脑局域网IP>:8000` 访问。
- 停止：在运行窗口按 `Ctrl+C`（不要用 `taskkill /IM python.exe`，会杀掉机器上其他 Python 程序）。
- 数据库在 `D:\data\cet4.db`（`config.py` 检测到 `/data` 存在就用它；Windows 上 `/data` 解析到当前盘符根目录）。

## 本地开发（改前端代码时才需要）

### 后端
```bash
cd backend
pip install -r requirements.txt
cp app/.env.example app/.env  # 填入 AI API Key
uvicorn app.main:app --port 8000
```

### 前端（开发服务器，热更新）
```bash
cd frontend
npm install
npm run dev        # 读 .env.development 里的 NEXT_PUBLIC_API_URL 跨端口访问后端
```
访问 http://localhost:3000

### 改完前端要让 http://localhost:8000 生效
后端托管的是**构建产物** `backend/static/`，必须在构建后同步一次，否则 8000 上仍是旧页面：
```bash
cd frontend
npm run build                                  # 产物在 frontend/out/
rm -rf ../backend/static && cp -r out ../backend/static
```

> 注意：`.env.local` 在 `next build`（生产构建）时也会被加载并内联，曾导致产物把 API 地址写死成
> `http://localhost:8000`，于是换 host/端口打开就没有数据。开发用地址现放在 `.env.development`，
> 生产构建里 `NEXT_PUBLIC_API_URL` 必须保持为空（同源相对路径 `/api/...`）。

### 回归测试
```bash
cd backend
python tests/test_static_routes.py     # 无需 pytest；校验静态路由、PWA 资源、产物不含写死的 API 地址
```

## 项目结构
```
cet4-flashcard/
├── backend/           # FastAPI 后端
│   ├── app/
│   │   ├── main.py           # 入口
│   │   ├── config.py         # 配置
│   │   ├── database.py       # 数据库
│   │   ├── models.py         # 数据模型
│   │   ├── routers/          # API 路由
│   │   ├── services/         # 业务逻辑
│   │   └── data/             # 词库 JSON
│   └── Dockerfile
├── frontend/          # Next.js 前端
│   ├── src/
│   │   ├── app/              # 页面
│   │   ├── components/       # 组件
│   │   └── lib/              # API 封装
│   └── package.json
└── README.md
```
