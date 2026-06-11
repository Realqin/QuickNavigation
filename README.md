# QuickNavigation

内网测试运维快捷导航平台：维护项目常用连接、按项目/环境展示卡片、接收 GitHub / 数据库变更推送。

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | React 18 + Vite + TypeScript + Ant Design |
| 后端 | Python 3.12 + FastAPI + SQLAlchemy |
| 数据库 | MySQL 8.0 |
| 部署 | Docker Compose |

## 快速启动

```bash
docker compose up -d --build
```

启动后访问：

- 前端首页：http://localhost:8080
- 后端 API：http://localhost:8000
- API 文档：http://localhost:8000/docs
- MySQL：localhost:3309

## 功能说明

### 1. 连接管理

- 字段：名称、URL、描述、环境、项目、类型（normal/github/database）、是否共用
- 支持按名称、项目、环境检索
- 路径：首页「连接管理」或 `/connections`

### 2. 首页导航

- 顶部切换项目、环境
- 上方折叠区：共用连接（所有项目可见）
- 下方折叠区：当前项目+环境下的连接
- 卡片支持拖拽排序、点击跳转、编辑

### 3. 日志订阅

- GitHub / GitLab：在「日志订阅」页复制 Webhook 地址。须配置 `PUBLIC_WEBHOOK_BASE_URL` 为 **GitLab 服务器能访问** 的地址，例如：
  ```
  # docker compose 部署（推荐内网）
  PUBLIC_WEBHOOK_BASE_URL=http://192.168.6.127:8080
  # 本地开发，GitLab 与你在同一局域网
  PUBLIC_WEBHOOK_BASE_URL=http://192.168.6.127:8000
  ```
  GitLab 项目 → Settings → Webhooks → URL 填：`http://<上述基址>/webhooks/gitlab`
- 数据库：
  - **结构巡检（推荐）**：日志订阅页 → 数据库连接 →「结构巡检」，填写数据库 IP、端口、账号、密码并启用。系统每 5 分钟对比 `information_schema` 快照，自动检测建库/建表/改表/删表，写入活动日志（不监听数据变更）。
  - **Webhook 上报**：应用侧变更后 POST：
  ```json
  POST /webhooks/database?secret=<webhook_secret>
  {
    "operation": "UPDATE",
    "table": "users",
    "summary": "批量更新测试账号",
    "rows_affected": 3,
    "author": "zhangsan"
  }
  ```
- 首页右侧实时展示当前项目/环境下的活动日志（WebSocket 推送）

## 目录结构

```
QuickNavigation/
├── docker-compose.yml
├── backend/          # FastAPI 后端
│   ├── app/
│   │   ├── main.py
│   │   ├── models.py
│   │   ├── routers/
│   │   └── ...
│   └── Dockerfile
└── frontend/         # React 前端
    ├── src/
    ├── nginx.conf
    └── Dockerfile
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| DATABASE_URL | MySQL 连接串 | docker-compose 内置 |
| GITHUB_WEBHOOK_SECRET | GitHub 签名密钥 | change-me-github-secret |
| GITLAB_WEBHOOK_SECRET | GitLab Secret token | change-me-gitlab-secret |
| PUBLIC_WEBHOOK_BASE_URL | Webhook 对外基址（GitLab 可访问） | 空 |
| SCHEMA_MONITOR_INTERVAL_SECONDS | 数据库结构巡检间隔（秒） | 300 |
| CORS_ORIGINS | 跨域来源 | * |

生产部署前请修改 `docker-compose.yml` 中的数据库密码和 `GITHUB_WEBHOOK_SECRET`。

## 本地开发

**后端（建议使用虚拟环境，避免与全局 Python 包冲突）：**

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt

# 先启动 MySQL（或 docker compose up mysql -d）
# 复制环境变量（可选，默认已指向 127.0.0.1:3309）
copy .env.example .env

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

在 `backend/.env` 中设置（把 IP 换成你本机局域网地址）：

```env
PUBLIC_WEBHOOK_BASE_URL=http://192.168.6.127:8000
```

**前端：**

```bash
cd frontend
npm install
npm run dev
```

Vite 已开启 `--host`，局域网可通过 `http://192.168.6.127:5173` 访问页面；**Webhook 仍应指向后端 8000 或 Docker 8080**，不要填 5173（除非仅作临时联调且 GitLab 能访问该地址）。

### 网络说明

| 场景 | 浏览器访问 | GitLab Webhook 填 |
|------|-----------|------------------|
| Docker 全栈 | `http://192.168.6.127:8080` | `http://192.168.6.127:8080/webhooks/gitlab` |
| 本地开发 | `http://192.168.6.127:5173` | `http://192.168.6.127:8000/webhooks/gitlab` |
| GitLab.com 公网 | 需公网域名或内网穿透 | `https://你的域名/webhooks/gitlab` |

若 `192.168.6.127:5173` 仍打不开，检查：① 前后端是否已启动；② Windows 防火墙是否放行 5173/8000/8080；③ 是否用了 `--host` / `0.0.0.0` 监听。

## 架构图

```mermaid
flowchart LR
    User["内网用户浏览器"] --> FE["Nginx + React :8080"]
    FE --> API["FastAPI :8000"]
    API --> DB[(MySQL)]
    GH["GitHub Webhook"] --> API
    App["业务应用 DB Hook"] --> API
    API --> WS["WebSocket /ws/logs"]
    WS --> FE
```
