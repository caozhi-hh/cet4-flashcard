# 腰子背单词 — Sealos 部署指南

> 合并部署：FastAPI 一个进程同时托管前端页面 + 后端 API + SQLite，单容器跑全站。
> 平台：Sealos（国内节点、Docker、按量计费、有免费额度）

---

## 一、前置准备

### 1. 注册 Sealos
访问 https://cloud.sealos.io （国内版）注册账号。

### 2. 准备代码仓库
把项目推到 GitHub / Gitee（Sealos 可从仓库自动构建，或本地构建镜像推送）：
```bash
cd d:/彭于晏/01-产品与开发/cet4-flashcard
git init && git add . && git commit -m "腰子背单词 v1.0"
git remote add origin <你的仓库地址>
git push -u origin main
```

> ⚠️ 确认 `.gitignore` 排除了 `.env`、`cet4.db`、`node_modules`、`backend/static`（前端产物在容器内构建）。

---

## 二、Sealos 部署（应用管理 → 部署容器）

### 方式 A：从镜像部署（推荐，最快）

#### 1. 在本地构建并推送镜像
```bash
# 登录 Sealos 镜像仓库（或用 Docker Hub / 阿里云ACR）
docker login

# 构建镜像（在项目根目录，Dockerfile 所在）
docker build -t yaozi-vocab:latest .

# 打标签推送（替换为你的镜像仓库地址）
docker tag yaozi-vocab:latest <你的仓库>/yaozi-vocab:latest
docker push <你的仓库>/yaozi-vocab:latest
```

#### 2. Sealos 控制台部署
进入 **应用管理 → 部署容器应用**：

| 配置项 | 值 |
|--------|-----|
| 镜像 | `<你的仓库>/yaozi-vocab:latest` |
| 容器端口 | `8000` |
| 对外访问 | 开启，类型选 **HTTP** 或绑定**自定义域名** |
| CPU/内存 | 0.5核 / 512MB（小项目够用，可后续调） |

---

## 三、关键配置：持久卷 + 环境变量

### 1. 持久卷（存 SQLite，重启不丢数据）
**应用详情 → 存储卷 → 添加**：

| 挂载路径 | 容量 | 用途 |
|---------|------|------|
| `/data` | 1Gi | SQLite 数据库 `cet4.db` |

> 容器内 `/data/cet4.db`，config.py 自动检测 `/data` 存在则用它。

### 2. 环境变量（密钥别硬编码到镜像）
**应用详情 → 环境变量 → 添加**：

| 变量名 | 值 | 说明 |
|--------|-----|------|
| `AI_API_KEY` | `sk-xxxxx` | 通义千问 key（**必填**，AI 功能依赖） |
| `AI_BASE_URL` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | 通义千问地址 |
| `AI_MODEL` | `qwen-turbo` | 模型 |
| `SITE_URL` | `https://vocab.yaozhi21.com` | 你的备案域名（自动加 CORS 白名单） |

> Sealos 支持「保密变量」(Secret)，AI_API_KEY 用 Secret 类型，不在日志显示。

---

## 四、绑定自定义域名（你的备案域名）

### 1. 在 Sealos 添加域名
**应用详情 → 网络 → 添加自定义域名**：
- 填入你的备案域名 `vocab.yaozhi21.com`
- Sealos 给一个 CNAME 地址

### 2. DNS 解析
到你的域名服务商（阿里云/腾讯云 DNS）：
- 添加 **CNAME 记录**：`vocab` → Sealos 给的 CNAME 地址

### 3. HTTPS 证书
Sealos 支持自动申请 Let's Encrypt 免费证书，勾选即可。

---

## 五、验证部署

部署成功后访问 `https://vocab.yaozhi21.com`：

```bash
# 健康检查
curl https://vocab.yaozhi21.com/api/health
# 应返回 {"status":"ok"}

# 词库加载（首次启动会从 cet4_words.json 导入 4544 词，约 2-3 秒）
curl https://vocab.yaozhi21.com/api/progress/overview
# 应返回 total_words: 4544

# 首页
curl -I https://vocab.yaozhi21.com/
# 应返回 HTTP 200
```

浏览器访问，确认：
- ✅ 首页「腰子背单词」加载
- ✅ 学习页能出单词
- ✅ AI 生成词书能用（验证 AI_API_KEY 生效）
- ✅ 收藏/测验数据持久（重启容器后还在 = 持久卷生效）

---

## 六、常用运维

| 操作 | 命令/位置 |
|------|----------|
| 查看日志 | Sealos 控制台 → 应用 → 日志（看 uvicorn 输出） |
| 重启应用 | 控制台 → 重启（SQLite 不丢，持久卷） |
| 更新版本 | 推新镜像 → 重新部署（数据保留） |
| 备份数据 | 定期拷贝 `/data/cet4.db` |
| 调整资源 | CPU/内存不足时在控制台扩容 |

---

## 七、成本估算（按量计费）

| 资源 | 配置 | 月成本（估算） |
|------|------|--------------|
| CPU | 0.5 核（按需） | ~¥5-15 |
| 内存 | 512MB | ~¥5-10 |
| 持久卷 | 1GB | ~¥1-2 |
| 流量 | 小项目 | ~¥2-5 |
| **合计** | | **~¥15-30/月** |

> 有免费额度可抵扣，初期可能免费。学习项目够用。

---

## 八、故障排查

| 问题 | 排查 |
|------|------|
| 首页 502/起不来 | 看日志，多为依赖/端口问题。确认容器端口 8000 |
| AI 生成失败 | AI_API_KEY 未配或无效，检查环境变量 |
| 数据重启丢失 | 持久卷未挂载到 `/data` |
| 词库 0 词 | cet4_words.json 未打进镜像（检查 COPY） |
| 域名打不开 | DNS CNAME 未生效（等 10 分钟）或域名未备案 |
