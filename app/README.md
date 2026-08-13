# Agent RAG 前端

基于 **Umi Max + Ant Design 5 + TypeScript** 的智能问答平台前端，对接 `agent-rag-app` 后端。

## 技术栈

| 模块 | 技术 |
|------|------|
| 框架 | Umi Max 4 (React 18) |
| UI 组件 | Ant Design 5 |
| 语言 | TypeScript 5 |
| Markdown 渲染 | react-markdown + remark-gfm |
| 请求 | @umijs/max 内置 request |

## 目录结构

```
app/
├── package.json
├── .umirc.ts                # Umi 配置(路由/代理/插件)
├── tsconfig.json
├── .env                     # 环境变量
├── public/
└── src/
    ├── app.tsx              # 运行时配置(请求拦截/错误处理)
    ├── global.less          # 全局样式
    ├── layouts/
    │   └── index.tsx        # 侧边栏布局 + 后端健康检查
    ├── services/
    │   └── api.ts           # 后端 API 封装(全部接口 + 类型定义)
    └── pages/
        ├── index.tsx        # 仪表盘(系统概览)
        ├── chat/
        │   └── index.tsx    # 智能对话(多轮 + Function Call 展示)
        ├── documents/
        │   └── index.tsx    # 文档管理(上传去重/列表/下载/预览/删除)
        └── knowledge/
            └── index.tsx    # 知识库(统计/检索测试/清空)
```

## 快速开始

### 1. 安装依赖

```bash
cd C:\Users\KK\WorkBuddy\Agent\app
npm install
```

> 如果 npm 较慢, 可用淘宝镜像: `npm config set registry https://registry.npmmirror.com`

### 2. 启动后端

确保 `agent-rag-app` 后端已启动(默认 `http://localhost:8000`):

```bash
cd C:\Users\KK\WorkBuddy\Agent\agent-rag-app
docker-compose up -d
```

### 3. 启动前端开发服务器

```bash
npm run dev
```

启动后访问 **http://localhost:8001** (Umi 默认端口, 如被占用会自动递增)。

### 4. 构建生产版本

```bash
npm run build
```

构建产物在 `dist/` 目录, 可用任意静态服务器托管。

## 页面说明

### 仪表盘 `/dashboard`
- 后端健康状态、知识库向量数、文档总数、记忆后端
- 快速入口按钮

### 智能对话 `/chat`
- 多轮对话, 自动维护 session_id
- RAG 开关: 启用后 Agent 自动检索知识库
- 工具调用展示: 显示 Agent 调用了哪些工具(knowledge_search 等)
- Markdown 渲染助手回复
- 新建会话 / 加载历史 / 清空会话
- Enter 发送, Shift+Enter 换行

### 文档管理 `/documents`
- 拖拽上传(支持 PDF/TXT/MD/DOCX), 自动 MD5 去重
- 文档列表表格: 文件名/大小/向量数/文本块/MD5/状态/时间
- 操作: 在线预览 / 下载 / 删除(三方联动: MinIO + Milvus + 数据库)
- 统计卡片: 文档数 / 文本块总数 / 向量总数

### 知识库管理 `/knowledge`
- 知识库统计(集合名 + 向量总数)
- 检索测试: 直接向量检索(不经过 Agent), 验证入库效果
- 清空知识库(危险操作, 二次确认)

## 接口对接

所有接口封装在 `src/services/api.ts`, 通过 Umi 内置 `request` 调用。

开发环境通过 `.umirc.ts` 中的 `proxy` 配置把 `/api` 代理到后端 `http://localhost:8000`, 无需处理跨域。

| 前端功能 | 后端接口 |
|---------|---------|
| 发送消息 | POST /api/chat |
| 会话历史 | GET /api/chat/history/{session_id} |
| 新建会话 | POST /api/chat/new-session |
| 清空会话 | DELETE /api/chat/{session_id} |
| 上传文档 | POST /api/documents/upload |
| 文档列表 | GET /api/documents |
| 文档详情 | GET /api/documents/{doc_id} |
| 下载文档 | GET /api/documents/{doc_id}/download |
| 预览文档 | GET /api/documents/{doc_id}/preview |
| 删除文档 | DELETE /api/documents/{doc_id} |
| 知识库统计 | GET /api/kb/stats |
| 清空知识库 | DELETE /api/kb/collection |
| 检索测试 | POST /api/kb/search |
| 健康检查 | GET /health |

## 生产部署

构建后将 `dist/` 部署到 Nginx, 配置反向代理转发 `/api` 到后端:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        root /path/to/app/dist;
        try_files $uri $uri/ /index.html;
    }

    location /api {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## 常见问题

**Q: 启动后端口是多少?**
A: Umi 默认 8000, 但后端也用 8000, 所以前端会自动用 8001。如需指定, 在 `.umirc.ts` 加 `npmClient` 旁的 `devServer: { port: 8001 }`。

**Q: 后端离线怎么办?**
A: 顶部会显示"后端: 离线"标签。确认后端服务已启动, 且 `.umirc.ts` 中 proxy target 指向正确地址。

**Q: 上传报错?**
A: 检查后端 DashScope API Key 是否配置正确, 文档解析需要向量化调用 DashScope。
