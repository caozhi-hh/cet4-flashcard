# 四级词汇闪卡

AI 驱动的大学英语四级词汇学习工具。

## 功能
- 📖 每天学习 20 个新词，闪卡翻转记忆
- 💡 AI 生成记忆口诀（拆分联想 + 谐音 + 情境）
- 🔄 间隔重复复习，不认识的词反复出现
- ✏️ 每日测验（选择题 + 填空题）
- 📊 学习进度统计

## 技术栈
- **后端**: FastAPI + SQLite + 通义千问 API
- **前端**: Next.js + Tailwind CSS
- **部署**: HF Spaces (后端) + Cloudflare Pages (前端)

## 本地开发

### 后端
```bash
cd backend
pip install -r requirements.txt
cp app/.env.example app/.env  # 填入 AI API Key
uvicorn app.main:app --port 8000
```

### 前端
```bash
cd frontend
npm install
npm run dev
```

访问 http://localhost:3000

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
