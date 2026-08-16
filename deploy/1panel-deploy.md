# Agent RAG App - 1Panel 生产部署指南

> 目标: 把整套系统(前端 + FastAPI + Milvus + MinIO + Redis + MySQL)以 Docker Compose 方式部署到 1Panel 管理的服务器, 通过反向代理对外提供 HTTPS 访问。

---

## 1. 部署拓扑

```
客户端 ──HTTPS──> 1Panel 反向代理(Nginx) ──> agent-rag-app:8000
                                              │
        ┌─────────────── 内部网络 agent-rag-net ───────────────┐
        │                                                      │
   [app] FastAPI+前端                                       [minio] 对象存储
        │                                                      │
   [milvus] 向量库(依赖 etcd + minio)                      [mysql] 长期记忆
        │                                                      │
   [redis] 会话记忆                                          [etcd] Milvus 元数据
```

- 对外仅暴露 **8000** 端口(或经反向代理 443)。
- MySQL(3306)、Redis(6379)、MinIO(9000/9001)、Milvus(19530) **只绑定 127.0.0.1**, 不暴露公网。

## 2. 服务器准备

1. 安装 Docker + Docker Compose(1Panel 可一键安装 Docker):
   - 1Panel 面板 → 「设置 → Docker」→ 一键安装(若未安装)。
2. 安装 1Panel 后, 通过面板管理 Docker 容器与反向代理。

## 3. 上传项目 / 制作镜像(二选一)

### 方式 A: 服务器上直接构建(推荐, 无需本机 Docker)

1. 把项目上传到服务器(可先排除 .venv / node_modules / data):
   ```bash
   # 在项目根目录执行(本地电脑):
   tar --exclude=.venv --exclude=node_modules --exclude=frontend/node_modules \
       --exclude=data --exclude=.git -czf agent-rag-app.tar.gz .
   scp agent-rag-app.tar.gz root@<服务器IP>:/opt/
   ```
2. 服务器上解压:
   ```bash
   mkdir -p /opt/agent-rag-app && tar -xzf /opt/agent-rag-app.tar.gz -C /opt/agent-rag-app
   cd /opt/agent-rag-app
   ```
3. 准备生产环境变量:
   ```bash
   cp deploy/.env.production .env
   vi .env        # 填入真实 DASHSCOPE_API_KEY, 并修改 MinIO/MySQL 密码
   ```
4. 构建并启动:
   ```bash
   docker compose up -d --build
   ```
   > 首次构建会联网拉取 Node/Python 基础镜像并执行 `npm ci` + `pip install`, 约需 5~15 分钟。

### 方式 B: 本机构建镜像后推送(服务器网络受限时)

```bash
# 本机(需 Docker Desktop):
docker build -t agent-rag-app:latest .
docker save agent-rag-app:latest | gzip > agent-rag-app.tar.gz
scp agent-rag-app.tar.gz root@<服务器IP>:/opt/
# 服务器:
docker load < /opt/agent-rag-app.tar.gz
cd /opt/agent-rag-app && cp deploy/.env.production .env && vi .env
docker compose up -d --no-build
```

## 4. 通过 1Panel 管理 Compose(替代命令行)

1. 1Panel → 「容器 → 编排」→「创建编排」。
2. 项目类型选 **Docker Compose**;把项目里的 `docker-compose.yml` 内容粘贴进编辑器。
3. 在「环境变量」区域把 `.env` 中的变量逐项填入(或直接在编排目录放 `.env` 文件)。
4. 保存后点击「构建 + 启动」。1Panel 会自动执行 `docker compose up -d --build`。

## 5. 反向代理 + HTTPS(对外提供域名访问)

1. 1Panel → 「网站 → 反向代理」→ 创建。
2. 填写:
   - 域名: `rag.example.com`
   - 代理地址: `http://127.0.0.1:8000`(app 容器映射到宿主机 8000)
   - 开启 HTTPS(1Panel 可自动申请 Let's Encrypt 证书)。
3. 前端是 SPA, 由后端 FastAPI 托管, 无需额外配置静态目录; `/` 返回 index.html, `/api/*` 走后端接口。

## 6. 数据持久化与备份

Compose 已声明命名卷, 容器删除后数据仍在:

| 卷 | 用途 |
|----|------|
| `mysql_data` | MySQL 长期记忆表 |
| `milvus_data` | Milvus 向量数据 |
| `etcd_data` | Milvus 元数据 |
| `minio_data` | 上传文档 + 技能产物 |
| `redis_data` | 会话记忆(AOF) |
| `app_data` | 应用运行期数据(uploads) |

备份建议(每周):
```bash
docker exec agent-rag-mysql sh -c 'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" agent_rag' > /opt/backup/agent_rag_$(date +%F).sql
```
MinIO/Milvus 数据卷可用 1Panel 的「卷备份」功能整体备份。

## 7. 升级流程

```bash
cd /opt/agent-rag-app
git pull                 # 拉取新代码(或重新上传 tar)
docker compose up -d --build
docker image prune -f    # 清理旧镜像
```
> 数据库结构变更由 `app.main:lifespan` 启动时 `CREATE TABLE IF NOT EXISTS` 自动完成, 无需手工迁移。

## 8. 常见问题

| 现象 | 排查 |
|------|------|
| 服务一直重启 / 健康检查失败 | `docker compose logs app` 查看; 确认 `.env` 中 DASHSCOPE_API_KEY 已填 |
| 上传文档报 500 `Embedding 失败` | 确认 DashScope API Key 有效、模型名正确; 阿里云百炼开通文本向量服务 |
| MySQL 连接失败 | 首次启动 MySQL 初始化需 30s+, app 已配置 depends_on 等待健康检查; 若仍失败 `docker compose logs mysql` |
| 9001 MinIO 控制台访问 | 仅本机可访问: 在服务器 SSH 执行 `curl http://127.0.0.1:9001` 或 SSH 隧道转发 |
| 前端页面 404 | 确认镜像内存在 `/app/frontend/dist`; `docker compose exec app ls frontend/dist` |
| 端口冲突 | 在 `.env` 调整映射或改 docker-compose 端口段 |

## 9. 安全清单

- [ ] `.env` 修改默认密码(MinIO / MySQL), 不要提交到 Git
- [ ] 1Panel 防火墙仅开放 80/443(及 SSH)
- [ ] DashScope API Key 使用最小权限(如有子 Key 则用子 Key)
- [ ] 定期备份 mysql_data / minio_data / milvus_data
- [ ] 升级时先备份, 再 `docker compose up -d --build`
