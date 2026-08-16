# Agent RAG App

基于 **FastAPI + RAG + Agent + Milvus + MinIO + MySQL + Redis + 通义千问** 的智能问答后端系统，采用**三层记忆分层存储**架构。

## 架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                        客户端                                │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP
┌──────────────────────────▼──────────────────────────────────┐
│                    FastAPI 应用层                            │
│  ┌──────────┐  ┌────────────┐  ┌──────────────────────────┐ │
│  │ 对话接口  │  │ 文档上传    │  │ 知识库管理               │ │
│  │ /api/chat│  │ /api/docs  │  │ /api/kb                  │ │
│  └────┬─────┘  └─────┬──────┘  └───────────┬──────────────┘ │
└───────┼──────────────┼─────────────────────┼────────────────┘
        │              │                     │
┌───────▼──────────────▼─────────────────────▼────────────────┐
│                       业务核心层                              │
│  ┌─────────────────────┐    ┌─────────────────────────────┐ │
│  │   Agent 模块         │    │       RAG 模块              │ │
│  │  • Function Call     │    │  • 文档加载                 │ │
│  │  • 工具调用循环       │◄──►│  • 文本切分                 │ │
│  │  • 多轮对话记忆       │    │  • 向量化                   │ │
│  └──────────┬──────────┘    │  • 向量库检索               │ │
│             │               └─────────────┬───────────────┘ │
└─────────────┼─────────────────────────────┼─────────────────┘
              │                             │
┌─────────────▼─────────────────────────────▼─────────────────┐
│                      基础设施服务层                           │
│  ┌────────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐  │
│  │ DashScope  │  │  Milvus  │  │  MinIO   │  │   Redis   │  │
│  │ 通义千问LLM │  │ 向量数据库│  │ 文件存储  │  │ 会话记忆   │  │
│  └────────────┘  └──────────┘  └──────────┘  └───────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## 目录结构

```
agent-rag-app/
├── docker-compose.yml          # 基础设施编排(Milvus/MinIO/Redis/App)
├── Dockerfile                  # 应用镜像
├── requirements.txt            # Python 依赖
├── .env.example                # 环境变量模板
├── README.md
├── data/
│   └── uploads/                # 本地上传临时目录
├── skills_catalog/             # 内置技能商店(8 个开箱即用技能 + 模板资产)
├── frontend/                   # React 前端(umi + antd, 科技苹果风毛玻璃 UI)
└── app/
    ├── main.py                 # FastAPI 入口 + 生命周期管理
    ├── config.py               # 统一配置(pydantic-settings)
    ├── agent/                  # Agent 模块
    │   ├── core.py             #   Agent 核心(Function Call 循环)
    │   ├── tools.py            #   工具定义 + Schema
    │   └── memory.py           #   短期会话记忆(Redis 滑动窗口+摘要压缩+TTL)
    ├── rag/                    # RAG 模块(第三层: 知识库记忆)
    │   ├── loader.py           #   文档加载(PDF/TXT/MD/DOCX)
    │   ├── splitter.py         #   文本切分(6种方式: 递归/固定/语义/结构/句子/LLM)
    │   ├── embedder.py         #   向量化(DashScope Embedding)
    │   ├── retriever.py        #   向量库检索
    │   └── reranker.py         #   LLM 重排器
    ├── services/               # 基础设施服务封装
    │   ├── dashscope.py        #   通义千问(OpenAI兼容接口/SSE流式/Embedding)
    │   ├── milvus.py           #   Milvus 向量库(MilvusClient API)
    │   ├── minio.py            #   MinIO 文件存储
    │   ├── database.py         #   文档/会话元数据(MD5去重/删查)
    │   ├── mysql.py            #   MySQL 连接池(自动建表: documents/rag_config/chat_sessions/long_term_memories/skills)
    │   ├── config_store.py     #   RAG 配置存储(MySQL持久化 + 初始化引导 + 嵌入模型锁定)
    │   ├── session_store.py    #   会话元数据存储(MySQL)
    │   ├── long_term_memory.py #   长期记忆(MySQL+Milvus/去重/衰减/沉淀)
    │   ├── skill_store.py      #   技能存储(商店目录/安装/导入/卸载/资产)
    │   ├── skill_artifacts.py  #   技能产物(MD/PDF导出/下载/TTL清理)
    │   └── evaluation.py       #   RAG 五维度评测服务
    ├── api/                    # API 接口层
    │   ├── chat.py             #   对话(流式SSE+会话管理)
    │   ├── documents.py        #   文档管理(上传去重/删查/访问)
    │   ├── knowledge_base.py   #   知识库管理(统计/检索/清空)
    │   ├── config.py           #   RAG 配置管理
    │   ├── evaluation.py       #   RAG 评测接口
    │   ├── memory.py           #   长期记忆管理(增删改查/检索/沉淀/遗忘)
    │   └── skills.py           #   技能管理(商店/安装/导入/启停/卸载/资产/产物)
    └── models/
        └── schemas.py          #   Pydantic 请求/响应模型
```

## 技术栈

| 模块 | 技术 | 说明 |
|------|------|------|
| Web 框架 | FastAPI | 异步 HTTP 接口，自动 OpenAPI 文档，SSE 流式输出 |
| 大模型 | 通义千问 DashScope | OpenAI 兼容接口，qwen3.7-plus 对话 + text-embedding-v3 向量化 |
| Agent | Function Call | 大模型原生函数调用，工具循环 |
| **技能系统** | **内置商店 + 自定义导入** | **指令型技能(SKILL.md)，显式/隐式触发，文档导出 MD/PDF** |
| **短期记忆** | **Redis** | **滑动窗口 + 摘要压缩 + 会话 TTL，分布式安全** |
| **长期记忆** | **MySQL + Milvus** | **结构化存储 + 语义召回，user_id 隔离，相似度去重，时间衰减遗忘** |
| **RAG 知识库** | **Milvus(独立集合)** | **业务文档检索，独立于对话记忆** |
| 向量数据库 | Milvus 2.4 | IVF_FLAT 索引，COSINE 相似度，MilvusClient API |
| 文件存储 | MinIO | S3 兼容对象存储 |
| PDF 生成 | xhtml2pdf + reportlab | Markdown→HTML→PDF，系统中文字体，缺失降级 MD |
| 前端 | React + umi + antd | 科技苹果风毛玻璃 UI，SSE 流式打字机 |
| 文档/会话/配置元数据 | MySQL | MD5 去重 + 全部结构化元数据(自动建表) |
| 编排 | Docker Compose | 一键启动全部服务(Milvus/MinIO/Redis/MySQL/App) |

## 三层记忆分层存储架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        用户对话                                      │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│  第一层: 短期会话记忆 (Redis)                                        │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ • 存储单会话对话消息列表                                      │    │
│  │ • 滑动窗口: 保留最近 N 条消息 (默认 20)                       │    │
│  │ • 摘要压缩: 超窗口时用 LLM 摘要早期消息                       │    │
│  │ • 会话 TTL: 自动过期 (默认 24h)                               │    │
│  │ • 分布式安全: 禁止内存存储用于生产                             │    │
│  └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ 沉淀(consolidate)
┌──────────────────────────────▼──────────────────────────────────────┐
│  第二层: 长期记忆 (MySQL + Milvus)                                   │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ • MySQL: 记忆实体 CRUD + 重要度打分(LLM评估)                  │    │
│  │ • Milvus: 语义召回 (独立集合 long_term_memory)                │    │
│  │ • user_id 元数据过滤: 用户隔离                                 │    │
│  │ • 相似度去重: 新增时检索, 超阈值(0.85)跳过                     │    │
│  │ • 时间衰减遗忘: score = base × e^(-λ×days)                   │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  第三层: RAG 知识库记忆 (Milvus knowledge_base 集合)                 │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ • 独立于 Agent 对话记忆, 用于业务文档检索                      │    │
│  │ • 文档上传 → 切分 → 向量化 → Milvus                          │    │
│  │ • Agent 通过 knowledge_search 工具检索                       │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

### 记忆流转

| 场景 | 流转 |
|------|------|
| 对话进行中 | 消息写入**短期记忆**(Redis)，滑动窗口+摘要压缩控制上下文 |
| 对话结束/沉淀 | 调用 `/api/memory/consolidate` 从短期记忆提取关键信息→**长期记忆** |
| 长期记忆检索 | `/api/memory/search` 语义检索，带 user_id 隔离 + 时间衰减 |
| 业务文档问答 | Agent 调用 `knowledge_search` 工具→**RAG 知识库**(独立集合) |
| 定期遗忘 | `/api/memory/decay` 将低重要度记忆标记为 forgotten |

## 快速开始

### 1. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入你的 DashScope API Key
# DASHSCOPE_API_KEY=sk-xxxxxxxx
```

获取 DashScope API Key: https://dashscope.console.aliyun.com/

### 2. 一键启动

```bash
#docker 环境安装
docker-compose up -d

#进入minIO服务，创建Access Keys 填入 docker-compose 的 milvus 中
# 创建documents  Buckets


#uv环境安装
uv venv --python
.venv\Scripts\activate   
uv pip install -r requirements.txt

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

启动后会拉起以下服务：

| 服务 | 端口 | 用途 |
|------|------|------|
| FastAPI App | 8000 | 主应用 |
| Milvus | 19530 | 向量数据库(RAG知识库 + 长期记忆) |
| MinIO Console | 9002 | 文件管理 Web UI |
| MinIO S3 API | 9001 | 文件存储 API |
| Redis | 6379 | 短期会话记忆 |
| MySQL | 3306 | 长期记忆结构化存储 |

### 3. 查看服务状态

```bash
docker-compose ps
# 健康检查
curl http://localhost:8000/health
```

### 4. 访问 API 文档

浏览器打开: http://localhost:8000/docs (Swagger UI)

## API 接口

### 对话

```bash
# 多轮对话
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test-001",
    "message": "帮我从知识库里查一下什么是 RAG",
    "use_rag": true,
    "skills": [],            // 显式指定技能 name 列表(按钮触发)
    "auto_skill": true       // 是否允许模型按意图隐式调用已启用技能
  }'

# 获取会话历史
curl http://localhost:8000/api/chat/history/test-001

# 清空会话
curl -X DELETE http://localhost:8000/api/chat/test-001
```

### 文档管理（上传去重 / 删查 / 访问）

```bash
# 上传文档 -> MD5去重 -> 自动切分 -> 向量化 -> 存入 Milvus + 元数据入 SQLite
curl -X POST http://localhost:8000/api/documents/upload \
  -F "file=@your_document.pdf"
# 重复上传相同文件会返回 duplicated=true, 跳过入库

# 列出所有文档(含元数据: md5/大小/块数/向量数/时间)
curl http://localhost:8000/api/documents

# 查询单个文档详情
curl http://localhost:8000/api/documents/{doc_id}

# 下载文档(附件方式)
curl -OJ http://localhost:8000/api/documents/{doc_id}/download

# 在线预览文档(浏览器内联,适合 PDF/TXT)
# 浏览器打开: http://localhost:8000/api/documents/{doc_id}/preview

# 删除文档(MinIO文件 + Milvus向量 + 数据库记录 三方联动)
curl -X DELETE http://localhost:8000/api/documents/{doc_id}

# 检索测试(不经过 Agent)
curl -X POST http://localhost:8000/api/kb/search \
  -H "Content-Type: application/json" \
  -d '{"query": "什么是RAG", "top_k": 4}'
```

### 知识库管理

```bash
# 知识库统计
curl http://localhost:8000/api/kb/stats

# 清空知识库(重建集合)
curl -X DELETE http://localhost:8000/api/kb/collection
```

### 技能系统

```bash
# 内置商店目录(含已安装标记)
curl http://localhost:8000/api/skills/store

# 从商店安装技能(重复安装=覆盖更新)
curl -X POST http://localhost:8000/api/skills/install \
  -H "Content-Type: application/json" -d '{"name": "weekly-report"}'

# 导入自定义技能(.zip 内含 SKILL.md + 资产, 或单个 .md)
curl -X POST http://localhost:8000/api/skills/import -F "file=@my-skill.zip"

# 已安装列表 / 启停 / 卸载
curl http://localhost:8000/api/skills
curl -X PATCH http://localhost:8000/api/skills/{skill_id} -H "Content-Type: application/json" -d '{"enabled": false}'
curl -X DELETE http://localhost:8000/api/skills/{skill_id}

# 下载技能生成的文档(MD/PDF, 由对话中 export_document 产出)
curl -OJ "http://localhost:8000/api/skills/artifacts/download?object_name=skill-outputs/..."
```

## 技能（Skill）系统

在 RAG + Agent + 长期记忆之上扩展可插拔技能能力：

- **应用商店**：内置 8 个开箱即用技能（周报/会议纪要/PRD/技术方案/代码审查/SQL/翻译润色/工作总结），一键安装
- **自定义导入**：支持 ZIP（SKILL.md + 模板/资料资产）或单个 SKILL.md，含校验（大小/数量/zip-slip 路径穿越拦截/name 正则）
- **对话集成**：显式按钮选择触发 + 隐式语言触发（模型按用户意图自动调用 `skill_<name>` 工具）
- **文档导出**：技能生成内容可导出为 MD/PDF，存入 MinIO 返回下载链接，对话消息内展示下载按钮

技能为**指令型**（SKILL.md 说明 + 资产文件，不执行任意代码）；生成文件存 `skill-outputs/` 前缀，启动自动清理 >7 天产物。

SKILL.md 格式（YAML front-matter + Markdown 指令）：

```markdown
---
name: weekly-report          # 小写字母数字连字符, 1-64 位
display_name: 周报生成
description: 根据本周工作内容生成结构化周报  # 供模型判断何时隐式调用
version: 1.0.0
tags: [办公, 文档]
---
# 周报生成技能
（给大模型的执行指令...）
```

## 核心流程说明

### 文档入库流程 (RAG + MD5去重)

```
上传文件
  │
  ▼
计算 MD5 → 查 SQLite 数据库
  │
  ├─ 已存在 → 返回 duplicated=true, 跳过上传
  │
  ▼ 不存在
MinIO 存储 ──────────────────► 文件持久化
  │
  ▼
文档加载 (loader.py)
  │ PDF/TXT/MD/DOCX → 纯文本
  ▼
文本切分 (splitter.py)
  │ 递归字符切分 (chunk_size=500, overlap=50)
  ▼
向量化 (embedder.py)
  │ DashScope text-embedding-v3 (1024维)
  ▼
Milvus 存储 ──────────────────► 向量 + 元数据
  │
  ▼
SQLite 存储 ──────────────────► 文档元数据(md5/块数/向量数...)
```

### Agent 对话流程

```
用户消息
  │
  ▼
加载会话记忆 (memory.py)
  │
  ▼
构建 messages (system + history + user)
  │
  ▼
┌─────────────────────────────┐
│  调用通义千问 (带 tools)      │
└──────────────┬──────────────┘
               │
      ┌────────┴────────┐
      ▼                 ▼
  返回文本           返回 tool_calls
      │                 │
      │           执行工具 (tools.py)
      │           • knowledge_search
      │           • list_documents
      │           • kb_stats
      │                 │
      │           工具结果加入对话
      │                 │
      └─────► 再次调用大模型 (循环) ──┘
                (最多 8 轮)
                  │
                  ▼
            生成最终回复
                  │
                  ▼
          保存到会话记忆
                  │
                  ▼
            返回给用户
```

## 环境变量说明

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DASHSCOPE_API_KEY` | (必填) | 通义千问 API Key |
| `DASHSCOPE_CHAT_MODEL` | qwen-plus | 对话模型 |
| `DASHSCOPE_EMBED_MODEL` | text-embedding-v3 | 向量化模型 |
| `MILVUS_HOST` | milvus | Milvus 地址 |
| `MILVUS_PORT` | 19530 | Milvus 端口 |
| `MILVUS_COLLECTION` | knowledge_base | RAG 知识库向量集合名 |
| `MINIO_ENDPOINT` | minio:9000 | MinIO 地址 |
| `MINIO_BUCKET` | documents | 文件 bucket |
| `REDIS_URL` | redis://redis:6379/0 | Redis 连接(短期记忆) |
| `MEMORY_BACKEND` | redis | 短期记忆后端: redis(生产) / memory(仅开发) |
| `MYSQL_HOST` | mysql | MySQL 地址(长期记忆) |
| `MYSQL_PORT` | 3306 | MySQL 端口 |
| `MYSQL_USER` | agent | MySQL 用户 |
| `MYSQL_PASSWORD` | agentpassword | MySQL 密码 |
| `MYSQL_DATABASE` | agent_rag | MySQL 数据库 |
| `DB_PATH` | ./data/app.db | SQLite 文档/会话元数据 |
| `CHUNK_SIZE` | 500 | 文本切分块大小 |
| `CHUNK_OVERLAP` | 50 | 切分重叠字符数 |
| `RETRIEVAL_TOP_K` | 4 | RAG 检索返回数量 |
| `SHORT_TERM_WINDOW` | 20 | 短期记忆滑动窗口大小 |
| `SHORT_TERM_TTL` | 86400 | 短期记忆会话 TTL(秒) |
| `MEMORY_DEDUP_THRESHOLD` | 0.85 | 长期记忆相似度去重阈值 |
| `MEMORY_DECAY_LAMBDA` | 0.01 | 长期记忆时间衰减系数 |

## 记忆系统配置

系统默认使用**三层记忆**架构，开箱即用：

- **短期记忆** → Redis（`MEMORY_BACKEND=redis`，分布式安全，默认开启）
- **长期记忆** → MySQL + Milvus（自动初始化表和集合）
- **RAG 知识库** → Milvus `knowledge_base` 集合（独立于对话记忆）

如需在单机开发时降级为内存存储（不推荐生产）：
```
MEMORY_BACKEND=memory
```

### 长期记忆 API

```bash
# 新增长期记忆(自动评分+去重+向量化)
curl -X POST http://localhost:8000/api/memory \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user-001", "content": "用户喜欢用 Python 开发"}'

# 语义检索用户记忆(user_id 隔离 + 时间衰减)
curl -X POST http://localhost:8000/api/memory/search \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user-001", "query": "用户喜欢什么语言"}'

# 列出用户所有记忆
curl http://localhost:8000/api/memory/user-001

# 从短期会话记忆沉淀到长期记忆
curl -X POST http://localhost:8000/api/memory/consolidate \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user-001", "session_id": "session-xxx"}'

# 执行时间衰减遗忘(清理低重要度记忆)
curl -X POST http://localhost:8000/api/memory/decay?threshold=0.05

# 删除/更新单条记忆
curl -X DELETE http://localhost:8000/api/memory/{memory_id}
curl -X PATCH http://localhost:8000/api/memory/{memory_id} \
  -H "Content-Type: application/json" \
  -d '{"importance": 0.9}'
```

## 本地开发（不用 Docker 跑应用）

如果只想在本地跑 FastAPI 应用（基础设施仍用 Docker）：

```bash
# 1. 只启动基础设施
docker-compose up -d etcd minio minio-init milvus redis

# 2. 安装依赖
python -m venv venv && source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 3. 配置环境(指向 localhost)
cp .env.example .env
# 修改: MILVUS_HOST=localhost, MINIO_ENDPOINT=localhost:9001, REDIS_URL=redis://localhost:6379/0

# 4. 启动
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 常见问题

**Q: Milvus 启动后健康检查一直失败？**
A: Milvus 首次启动较慢，`start_period: 90s` 已预留时间，请耐心等待。`docker-compose logs milvus` 查看日志。

**Q: 上传文档后检索不到结果？**
A: 检查 `curl http://localhost:8000/api/kb/stats` 确认向量已入库；确认 `DASHSCOPE_API_KEY` 配置正确。

**Q: MinIO Console 账号密码？**
A: 默认 `minioadmin / minioadmin`，可在 docker-compose.yml 修改。
