# 腰子背单词

面向大学英语四级学习场景的全栈词汇平台，围绕“学习 → 复习 → 默写/测验 → 阅读应用”形成闭环，并用 FSRS-6 根据记忆表现安排后续复习。

**在线演示：** [https://cet4-flashcard.liam.blitz.cloud/](https://cet4-flashcard.liam.blitz.cloud/)

> 免费实例可能在空闲后休眠，首次访问需要等待数秒唤醒。AI 功能需要服务端配置模型密钥；其他学习功能不依赖 AI。

## 主要功能

- 邮箱注册登录、Argon2id 密码哈希、Cookie 会话与 CSRF 防护
- 按用户隔离学习记录、收藏、错题、词书、计划和阅读成绩
- FSRS-6 四档评分、到期复习、学习进度和连续学习统计
- 闪卡学习、默写、每日测验、生词本与错题本
- 四/六级等预置词书、AI 生成自定义词书、每日学习计划与完成预测
- A1/A2/B1 分级阅读、点词释义、理解题和阅读进度
- AI 记忆口诀；AI 接口按登录用户限流，密钥只保存在服务端
- 响应式界面、PWA 静态资源和深色模式

## 技术栈与架构

- 前端：Next.js 16、React 19、TypeScript、Tailwind CSS、Serwist
- 后端：FastAPI、SQLAlchemy 2、Pydantic、Uvicorn
- 数据：生产环境 Neon PostgreSQL；本地默认 SQLite
- 学习算法：FSRS-6
- AI：OpenAI 兼容接口，默认适配智谱 GLM
- 部署：根目录多阶段 Dockerfile，Blitz Cloud 单容器同源托管静态前端和 `/api/*`

```text
Browser / PWA
      │ same-origin HTTPS
      ▼
FastAPI + static Next.js export
      ├── Auth / CSRF / per-user isolation
      ├── FSRS learning services
      ├── AI proxy + per-user rate limit ──► OpenAI-compatible model
      └── SQLAlchemy ─────────────────────► Neon PostgreSQL
```

前端不会读取 AI 密钥，也不会直接请求模型供应商。`DATABASE_URL` 和 `AI_API_KEY` 仅由后端进程读取。

## 本地启动

### 一体化模式

根目录 Dockerfile 会构建前端并由 FastAPI 同源托管：

```bash
docker build -t cet4-flashcard .
docker run --rm -p 8000:8000 cet4-flashcard
```

打开 <http://localhost:8000>，健康检查为 <http://localhost:8000/api/health>。

### 开发模式

```bash
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

另开终端：

```bash
cd frontend
npm install
npm run dev
```

打开 <http://localhost:3000>。不设置 `DATABASE_URL` 时，后端自动使用本地 SQLite。

## 环境变量

| 变量 | 必需 | 默认值 / 用途 |
| --- | --- | --- |
| `DATABASE_URL` | 生产必需 | PostgreSQL 连接串；留空使用 SQLite |
| `AI_API_KEY` | 仅 AI 功能 | 模型供应商密钥，只能配置在服务端环境变量 |
| `AI_BASE_URL` | 否 | `https://open.bigmodel.cn/api/paas/v4/` |
| `AI_MODEL` | 否 | `glm-4-flash` |
| `AI_MNEMONIC_LIMIT` | 否 | 每用户每窗口最多 30 次记忆口诀请求 |
| `AI_WORDBOOK_LIMIT` | 否 | 每用户每窗口最多 5 次 AI 词书请求 |
| `AI_RATE_WINDOW_SECONDS` | 否 | 限流窗口 3600 秒 |
| `SESSION_TTL_DAYS` | 否 | 会话有效期 30 天 |
| `COOKIE_SECURE` | 否 | `auto`，HTTPS 下自动使用 Secure Cookie |
| `COOKIE_SAMESITE` | 否 | `lax` |
| `SITE_URL` | 否 | 自定义站点地址，用于补充 CORS 来源 |
| `ADMIN_TOKEN` | 管理接口 | 留空时管理写接口保持禁用 |

完整示例见 `backend/app/.env.example`。不要提交真实连接串或密钥。

AI 限流使用按用户、按接口的进程内滑动窗口，适合当前单实例演示部署；多实例部署时应改用 Redis 等共享存储。

## 测试与构建

```bash
cd backend
python -m pytest -q
```

```bash
cd frontend
npm run test:ui
npm run build
```

PostgreSQL 集成测试只允许连接可清空的独立测试库或测试分支，并要求显式确认；禁止指向生产数据库：

```bash
cd backend
TEST_DATABASE_URL="postgresql://...test..." TEST_DB_ACK="I_UNDERSTAND_THIS_DROPS_TABLES" python -m pytest -q tests/test_postgres_integration.py
```

## 项目结构

```text
cet4-flashcard/
├── backend/
│   ├── app/
│   │   ├── routers/       # 认证、学习、测验、词书、阅读与 AI API
│   │   ├── services/      # FSRS、AI、词书等业务逻辑
│   │   ├── data/          # 内置词库与分级阅读数据
│   │   ├── database.py    # SQLite / PostgreSQL 适配
│   │   └── main.py        # FastAPI 入口和静态资源托管
│   └── tests/
├── frontend/
│   ├── src/app/           # Next.js 页面
│   ├── src/components/    # 闪卡、导航、反馈与详情组件
│   └── tests/interaction/ # jsdom 交互回归测试
├── Dockerfile             # Blitz Cloud 使用的生产镜像
└── README.md
```
