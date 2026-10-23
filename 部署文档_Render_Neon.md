# Render + Neon 部署指南（免费档，无需银行卡）

> 架构：`GitHub(main)` → **Render Free Web Service**（跑仓库根 `Dockerfile`，前后端合并）
> → **Neon Free PostgreSQL**（账号 / 学习记录 / 计划 / 生词本 / 阅读记录 / 词库）。

## 一、Neon（PostgreSQL）

1. 打开 https://neon.tech ，用 GitHub 登录（免费档不需要银行卡）→ 新建 Project → 得到连接串：
   ```
   postgresql://<user>:<password>@<host>.neon.tech/<db>?sslmode=require
   ```
2. 建议建**两个库**（或两个 branch）：一个生产库（如 `neondb`）、一个测试库（名字**必须含 `test`**，
   供 `tests/test_postgres_integration.py` 使用；该套件会 `drop_all`，库名不含 test 会被拒绝执行）。

## 二、Render（Web Service）

1. New → **Web Service** → 连接仓库 `caozhi-hh/cet4-flashcard`（分支 `main`）。
2. Language 选 **Docker**（自动使用仓库根 `Dockerfile`）；Instance Type 选 **Free**。
3. **Health Check Path**：`/api/health`。
4. Environment 变量：

   | 变量 | 值 | 说明 |
   |---|---|---|
   | `DATABASE_URL` | Neon 连接串 | **必填**；不填会退回 SQLite（免费档文件系统不持久，等于每次重启清零） |
   | `AI_API_KEY` | 智谱 GLM key | 可选；不填则 AI 口诀/词书不可用，其余功能正常 |
   | `AI_BASE_URL` / `AI_MODEL` | `https://open.bigmodel.cn/api/paas/v4/` / `glm-4-flash` | 可选，有默认值 |
   | `ADMIN_TOKEN` | 随机串 | 可选；配置后才能调 `POST /api/words/init` |
   | `COOKIE_SECURE` | `auto` | 默认即可；Render 是 HTTPS，会自动给会话 Cookie 加 `Secure` |

5. 首次启动会自动建表并导入 4544 个词（约 10–30 秒）。日志里会打印数据库主机（**不含密码**）。

## 三、必须知道的几个差异

- **免费实例会休眠**：Render 免费档约 15 分钟无流量后休眠，冷启动约 30–60 秒；Neon 空闲也会挂起连接。
  代码里已用 `pool_pre_ping=True` + `pool_recycle=300` 处理，不会把坏连接交给请求。
- **备份不同**：SQLite 的文件级备份（`sqlite3` 在线备份 API）对 PostgreSQL **不适用且已被代码跳过**；
  PostgreSQL 请用 Neon 自带的 PITR / 分支备份。
- **结构变更不做自动化**：PostgreSQL 上不会执行 SQLite 那套 `ALTER TABLE` / 重建表；
  若线上库结构落后于模型，服务会**启动失败并打印需要执行的 SQL**（宁可失败，也不静默改结构）。
- **健康检查语义**：`/api/health` 始终返回 200（避免数据库瞬时抖动导致 Render 反复重启实例），
  但会把真实状态放进 `db` 字段：
  ```json
  {"status": "ok", "db": "ok", "backend": "postgresql"}
  ```

## 四、部署后验证

```bash
# 1) 健康检查：backend 必须是 postgresql
curl https://<your-service>.onrender.com/api/health

# 2) 注册 → 学一轮 → 在 Render 控制台 Restart → 再看进度是否还在
#    进度还在 = 数据确实落在 Neon，而不是容器的临时文件系统
```

## 五、已知未完成事项

- 本文档只是配置说明：**未创建 Neon 库、未创建 Render 服务、未部署**。
- **r18 镜像不能直接用**：`25a0028` 的 `backend/requirements.txt` 未声明 `argon2-cffi`，
  而 `auth.py` 启动即 `from argon2 import PasswordHasher`（且无依赖传递引入）
  → 容器启动会 `ModuleNotFoundError`。本分支已补上该依赖，需重新构建镜像后再部署。