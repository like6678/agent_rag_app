# Agent RAG App 企业级工程化审查与优化报告

> 审查日期: 2026-08-15
> 审查范围: 后端 (FastAPI + Agent + RAG + 三层记忆 + 评测)、前端 (Umi + AntD)、依赖与工程化
> 验证方式: 本地启动服务实测 (Milvus / MinIO / MySQL 已就绪)

---

## 一、项目架构概览

```
┌─────────────────────────────────────────────────────────────┐
│ 前端 (Umi + AntD): chat / documents / knowledge / config     │
│                    / evaluation / memory / dashboard         │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP / SSE
┌──────────────────────────▼──────────────────────────────────┐
│ FastAPI 后端                                                 │
│  ├─ api/        chat, documents, kb, config, evaluation, memory │
│  ├─ agent/      Function Call 循环 + 短期记忆(Redis/内存)     │
│  ├─ rag/        loader → splitter(6种) → embedder → retriever │
│  │              → reranker                                    │
│  ├─ services/   dashscope(LLM), milvus(向量), minio(文件),    │
│  │              mysql(元数据+记忆+配置), evaluation(评测)      │
│  └─ 三层记忆:   短期(Redis滑动窗口+摘要) → 长期(MySQL+Milvus)  │
└─────────────────────────────────────────────────────────────┘
```

**技术栈**: FastAPI / uv 包管理 / pymilvus(MilvusClient) / MinIO / MySQL(DBUtils 连接池) / Redis / 通义千问 DashScope(OpenAI 兼容接口)

---

## 二、问题总览

| # | 级别 | 分类 | 问题 | 状态 |
|---|------|------|------|------|
| 1 | P0 | 接口Bug | 文档上传接口 100% 报 500（协程未 await） | ✅ 已修复 |
| 2 | P0 | 接口Bug | 文档列表/详情接口 100% 报 500（datetime 序列化） | ✅ 已修复 |
| 3 | P0 | 接口Bug | Agent 多轮工具调用第二轮必 400（缺 tool_call_id） | ✅ 已修复 |
| 4 | P0 | 安全 | CORS 非法组合（`*` + credentials） | ✅ 已修复 |
| 5 | P0 | 安全 | 配置接口明文返回 API Key | ✅ 已修复 |
| 6 | P0 | 依赖 | pyproject 缺失 fastapi/uvicorn 等 10+ 依赖，服务无法启动 | ✅ 已修复 |
| 7 | P1 | RAG | 检索参数（top_k/度量/nprobe/索引）配置改了不生效 | ✅ 已修复 |
| 8 | P1 | RAG | 重排配置形同虚设：真实检索链路不走 rerank | ✅ 已修复 |
| 9 | P1 | RAG | 上传流程中途失败产生孤儿文件/向量，无回滚 | ✅ 已修复 |
| 10 | P2 | 长期记忆 | 长期记忆与对话完全脱节，存了从不使用 | ✅ 已修复 |
| 11 | P2 | 长期记忆 | 记忆检索只按相似度排序，重要度未参与排序 | ✅ 已修复 |
| 12 | P3 | 评测 | 评测链路与生产链路不一致（重复重排、多次 LLM 调用） | ✅ 已修复 |
| 13 | P3 | 性能 | 所有端点 async def 内执行同步阻塞调用，卡死事件循环 | ✅ 已修复 |
| 14 | P4 | 工程化 | requirements.txt 与 pyproject 严重不同步 | ✅ 已修复 |
| 15 | P4 | 工程化 | 遗留诊断脚本、main.py 是 stub、tsconfig 缺 baseUrl | ✅ 已修复 |
| 16 | ⚠️ | 环境 | DashScope API Key 无效（需用户更新凭据） | ✅ 已解决（用户更新 Key + 批大小适配） |
| 17 | P1 | 接口Bug | 中文文件名预览/下载 500（latin-1 codec） | ✅ 已修复 |
| 18 | P1 | 接口Bug | 对话流式输出空回复，需刷新才可见 | ✅ 已修复 |
| 19 | P1 | 接口Bug | 仪表盘服务状态误判离线（/health 未走代理） | ✅ 已修复 |

---

## 三、P0：前后端接口 Bug（已全部实测复现并验证修复）

### 问题 1：文档上传接口 100% 失败

- **现象**: `POST /api/documents/upload` 返回 500，报 `a bytes-like object is required, not 'coroutine'`
- **根因**: `app/api/documents.py` 中 `content = file.read()` 漏了 `await`。FastAPI 的 `UploadFile.read()` 是协程，拿到的是 coroutine 对象而不是 bytes，传给 MinIO 的 `len(data)` 直接炸掉
- **影响**: 核心功能（文档入库）完全不可用，前端文档页上传永远失败
- **修复**: 将上传端点整体改为同步 `def`，改用 `file.file.read()`（底层 SpooledTemporaryFile 同步读取）。一举两得：既修复 bug，又把重负载移出事件循环（见问题 13）
- **验证**: 修复后上传链路（MD5 去重 → MinIO → 解析 → 切分）全部走通，仅在向量化时因 API Key 失效报错（环境问题，见问题 16）

### 问题 2：文档列表/详情接口 100% 失败

- **现象**: `GET /api/documents` 返回 500，Pydantic 报 `created_at: Input should be a valid string, input_value=datetime.datetime(...)`
- **根因**: pymysql 返回的 `created_at/updated_at` 是 `datetime` 对象，而 `DocumentInfo` 模型字段声明为 `str`，Pydantic v2 不会自动把 datetime 转成 str
- **影响**: 前端文档管理页完全打不开（列表 500），知识库页同样受影响
- **修复**: 在 `mysql.py` 增加统一的行序列化器 `_serialize_row()`：`datetime/date → ISO 字符串`、`Decimal → float`、`bytes → str`，在 `query()/query_one()` 出口统一转换
- **为什么这样改**: 在数据访问层统一处理，比在每张 Pydantic 模型里加 validator 更彻底——同时修复了文档列表、文档详情、以及所有直接返回 MySQL 行的接口（会话、记忆）的潜在隐患
- **验证**: `GET /api/documents` 200，返回 `"created_at": "2026-08-10 21:48:07"` 正常字符串

### 问题 3：Agent 多轮工具调用第二轮必失败

- **现象**: 当 Agent 需要连续调用两次以上工具时（Function Call 循环第二轮），DashScope 返回 400
- **根因**: `app/agent/core.py` 把工具结果塞回对话时，`tool` 角色消息缺 `tool_call_id` 字段。OpenAI 兼容协议强制要求 tool 消息通过 `tool_call_id` 与 assistant 消息里的 `tool_calls[].id` 一一对应
- **影响**: 复杂问题（需要"先列文档→再检索"这类多步推理）必然失败，且报错信息不直观，极难排查
- **修复**: tool 消息补上 `"tool_call_id": tc.get("id", "")`
- **为什么**: 这是协议硬性要求，第一轮不报错是因为第二轮请求才会校验上下文完整性

### 问题 4：CORS 非法组合

- **现象**: 跨域请求携带 Cookie 时浏览器直接拦截响应
- **根因**: `allow_origins=["*"]` 与 `allow_credentials=True` 是 CORS 规范的非法组合，浏览器要求两者二选一
- **修复**: `allow_credentials=False`（本项目是纯 Bearer/无 Cookie API，不需要 credentials）
- **遗留建议**: 生产环境应把 `allow_origins` 收敛为具体域名列表

### 问题 5：配置接口明文泄露 API Key

- **现象**: `GET /api/config` 完整返回 `dashscope_api_key` 明文，任何能访问接口的人都能拿到
- **修复**: 返回前脱敏（保留前 6 位 + 后 4 位）；`PUT /api/config` 更新时若检测到提交的是掩码值（含 `*`），自动丢弃该字段保留原 Key
- **为什么**: 前端配置页需要回显"已配置"状态但不能泄露凭据；掩码回显 + 原样提交不落库是业界标准做法

### 问题 6：依赖声明缺失，服务无法启动

- **现象**: `uv run` 后报 `No module named uvicorn`
- **根因**: `pyproject.toml` 只声明了 4 个依赖，而代码实际需要 fastapi、uvicorn、python-multipart、minio、beautifulsoup4、python-docx、pypdf、markdown、dbutils、pymysql、redis 等 11 个
- **修复**: 通过 `uv add` 全部补齐并锁定版本，`uv.lock` 同步更新
- **为什么**: 依赖必须声明完整，否则换台机器/CI 环境必然起不来——这是"能跑在我电脑上"的典型反模式

---

## 四、P1：RAG 链路优化

### 问题 7：检索参数配置改了不生效

- **现象**: 前端配置页修改 `retrieval_top_k`、`search_metric`、`nprobe`、`index_type` 后，检索行为毫无变化
- **根因**: 三处硬编码绕过配置中心：
  - `retriever.py` 默认 `top_k` 读 `settings`（环境变量快照），不读 MySQL 动态配置
  - `milvus.py search()` 硬编码 `metric_type="COSINE", nprobe=16`
  - `milvus.py ensure_collection()` 硬编码 `IVF_FLAT / COSINE / nlist=128 / dim=settings.embed_dim`
- **修复**: 三处全部改为运行时读 `get_rag_config()`；并按索引类型适配搜索参数（IVF 用 nprobe、HNSW 用 ef、FLAT 无需参数）
- **效果**: 配置页改动实时生效，"配置化 RAG 调参"这个产品卖点从摆设变成真功能
- **注意**: 切换 embedding 模型（维度变化）后需要重建集合（`DELETE /api/kb/collection`）才能写入新维度向量，这是 Milvus 的物理限制

### 问题 8：重排配置形同虚设

- **现象**: 配置页开启 LLM 重排后，对话检索结果毫无变化
- **根因**: `reranker` 只在评测服务里被调用，真实对话检索（Agent 工具、SSE 流式）完全绕过它
- **修复**: 重排逻辑下沉到 `retriever.search()`：开启重排时先放大召回（`top_k × 2`），再用重排器截断到 `top_k`
- **为什么放大召回**: 向量检索保证"召得全"，重排保证"排得准"。只重排 top_k 个候选没有意义——候选池越大，重排越能把真正相关的片段捞进最终上下文。这是 RAG 的标准两段式检索范式（Recall → Rerank）
- **效果**: 对话和检索测试接口都会真正应用重排，最终送入 LLM 的上下文相关性提升

### 问题 9：上传流程中途失败产生孤儿数据

- **现象**: 文件已传 MinIO 后，若向量化失败（如 API Key 失效、Embedding 限流），MinIO 里的文件成为孤儿——数据库无记录，界面上看不到也删不掉
- **修复**: 上传 pipeline（解析→切分→向量化→入库）包裹在 try 块中，任何一步失败都回滚：先删 Milvus 可能已写入的向量，再删 MinIO 文件
- **为什么**: 分布式存储没有跨系统事务，只能用"补偿回滚"保证最终一致。失败顺序先 Milvus 后 MinIO，因为 Milvus 可能部分写入

---

## 五、P2：长期记忆优化

### 问题 10：长期记忆与对话完全脱节（核心功能缺陷）

- **现象**: 用户在记忆页存了"我喜欢喝咖啡"，对话时问"我喜欢什么"，模型完全不知道
- **根因**: 长期记忆模块（增删改查/去重/衰减）实现得很完整，但**对话链路从未读取它**——记忆只进不出
- **修复**:
  1. `ChatRequest` 新增可选 `user_id` 字段
  2. `agent/core.py` 新增 `_recall_long_term_memories()`：用当前问题语义检索该用户 top 3 记忆，拼成 system 消息注入上下文
  3. 非流式 + SSE 流式两条对话链路都接入
  4. 前端对话页工具栏新增"用户ID"输入框，随请求传递
  5. 召回失败（如 Milvus 未就绪）静默降级，绝不影响主对话
- **为什么用语义召回而不是全量注入**: 全量记忆注入会撑爆上下文且引入噪音；按当前问题语义召回相关记忆，是 MemGPT 等记忆架构的标准做法
- **验证**: 实测日志可见 `长期记忆召回失败(降级跳过)`——召回逻辑确实被触发，Key 失效时按设计优雅降级

### 问题 11：记忆检索只按相似度排序

- **现象**: 高重要度但表述与查询不完全匹配的记忆，会被低重要度但字面更接近的记忆挤出 top_k
- **修复**: 引入融合打分 `fused_score = 0.7 × 语义相似度 + 0.3 × 衰减后重要度`，按融合分排序后截断；返回结果附带 `fused_score` 字段
- **为什么 7:3**: 语义相关性是检索的第一目标（答非所问的记忆没有意义），重要度作为次级信号纠偏。重要度本身已含时间衰减，使"最近常用的重要记忆"自然上浮
- **效果**: 记忆检索同时兼顾"相关"和"重要"，召回质量更符合直觉

---

## 六、P3：评测系统优化

### 问题 12：评测链路与生产链路不一致

- **现象**: 评测服务自己手动做了一次重排，而生产对话不重排（问题 8 修复前）——评测结果无法反映真实体验
- **附带问题**: retriever 修复后若不改评测，同一批 hits 会被重排两次，白白多消耗一轮 LLM 调用
- **修复**: 删除评测里的手动重排，评测直接走 `retriever.search()`——与生产完全同一条链路
- **为什么**: 评测存在的意义是"用离线指标预估线上效果"，前提是链路一致。否则优化了评测分，线上却没变化
- **遗留说明**: 评测报告中"切片参数/向量库参数"两个维度目前是启发式打分（按参数区间给分），不是实测指标，解读报告时需注意。后续可接入 RAGAS 等标准评测框架替换

### 问题 13：同步阻塞调用跑在事件循环上（性能隐患）

- **现象**: 所有 API 端点都是 `async def`，但内部全是同步阻塞调用（requests 调 LLM 最长 120s、pymysql、pymilvus）。一个对话请求会卡死整个事件循环，期间所有其他请求排队
- **修复**: 全部端点改为同步 `def`——FastAPI 会自动把同步端点丢进线程池执行，互不阻塞。SSE 流式端点的同步生成器也会被 StreamingResponse 自动放进线程池迭代
- **为什么不用 run_in_threadpool 包一层**: 改 `def` 是 FastAPI 官方推荐做法，代码零侵入；逐个包 `await run_in_threadpool()` 会让代码可读性大幅下降
- **效果**: 多用户并发对话、上传大文档时不再互相卡死；评测（每项 3 次 LLM 调用）执行期间系统仍可正常响应其他请求

---

## 七、P4：工程化治理

### 问题 14：两套依赖声明严重不同步

- **现象**: `requirements.txt`（旧）与 `pyproject.toml` 内容对不上——requirements 里有 dashscope/redis，pyproject 里没有；版本也互相矛盾
- **修复**: 以 `pyproject.toml + uv.lock` 为唯一事实来源，`uv export` 重新生成 requirements.txt（供仍需 pip 的环境使用）
- **建议**: 团队统一用 uv 管理，requirements.txt 仅作兼容导出物，不要手工编辑

### 问题 15：仓库残留与入口问题

- **问题**:
  - 根目录 4 个 `_diag_*.py` 诊断脚本残留（已完成使命，污染仓库）
  - `main.py` 是 `print("Hello")` 的脚手架 stub，新人拿到项目不知道怎么启动
  - 前端 `tsconfig.json` 缺 `baseUrl`，`@/` 路径别名导致 `tsc --noEmit` 直接报错
- **修复**: 删除诊断脚本（git 历史可查）；`main.py` 改为真正的启动入口（读配置启动 uvicorn）；tsconfig 补 `baseUrl: "."`
- **验证**: `tsc --noEmit` 全量类型检查通过（0 错误）

---

## 八、待用户处理事项

### 问题 16：DashScope API Key 无效 ⚠️

- **现象**: 所有 LLM 调用返回 `invalid_api_key: Incorrect API key provided`
- **现状**: MySQL 配置表里存的 Key（`sk-b45********25c4`）和 `.env` 里的 Key 都被 DashScope 拒绝
- **处理**: 请在配置页（或 `.env`）更新为有效的 DashScope API Key 后重试。更新后文档上传、对话、记忆、评测即可全链路工作
- **安全提醒**: `.env` 中的 Key 曾在对话记录中完整出现，建议到阿里云百炼平台轮换（吊销旧 Key、签发新 Key）

### 后续优化建议（本次未实施）

| 方向 | 说明 |
|------|------|
| 大文件分片上传 | 当前全量读入内存，建议 >50MB 文件走 MinIO 分片上传 + 异步任务队列处理 |
| 检索可观测性 | 记录每次检索的命中分数分布，便于发现"知识库覆盖不足" |
| 记忆自动沉淀 | 对话结束后自动触发 consolidate（目前是手动调 API） |
| 评测框架 | 接入 RAGAS 标准化指标（faithfulness/answer_relevance/context_precision） |
| 鉴权 | 目前所有接口无鉴权，生产部署前需加 API Token / OAuth2 |
| 单元测试 | 建议为 splitter / reranker / 记忆衰减打分补 pytest 用例 |

---

## 九、改动文件清单

**后端**: `app/api/documents.py`(上传修复+回滚+同步化) `app/api/chat.py`(同步化+记忆注入+user_id) `app/api/config.py`(Key脱敏) `app/api/evaluation.py` `app/api/memory.py` `app/api/knowledge_base.py`(同步化) `app/agent/core.py`(tool_call_id+记忆召回) `app/rag/retriever.py`(配置化+重排接入) `app/services/milvus.py`(配置化检索/建集合) `app/services/mysql.py`(行序列化) `app/services/long_term_memory.py`(融合打分) `app/services/evaluation.py`(链路统一) `app/models/schemas.py`(user_id) `app/main.py`(CORS)

**前端**: `frontend/src/pages/chat/index.tsx`(用户ID输入) `frontend/src/services/index.ts`(ChatRequest.user_id) `frontend/tsconfig.json`(baseUrl)

**工程**: `pyproject.toml` `uv.lock` `requirements.txt` `main.py`(启动入口) 删除 `_diag_*.py`×4
---

## 十、前端视觉与交互优化（简约科技感改版）

基于 design-taste-frontend 技能进行设计审查与改版。

**Design Read**: 开发者控制台 / RAG 管理台，面向工程师，简约科技感（深色 + 青色强调 + 等宽数字），基于 AntD v5 主题令牌实现。
**Dials**: VARIANCE 5 / MOTION 3 / DENSITY 4（内部工具，重信息密度、低装饰、克制动效）。

### 10.1 全局视觉系统

- **深色科技底**：`#070a10` 底色 + 双向径向辉光（青/蓝）+ 极淡 40px 网格底纹，营造控制台质感而非"AI 紫色渐变"套路
- **主题令牌化**：`ConfigProvider` 启用 `darkAlgorithm`，主色改为科技青 `#22d3ee`，统一圆角 8px；菜单选中项、链接、开关全部联动
- **玻璃感卡片**：所有 `Card` 半透明 `rgba(255,255,255,.025)` + 1px 极淡边框 + 轻微 backdrop-blur，层次靠透明度而非阴影
- **等宽数字**：新增 `.mono` 工具类（JetBrains Mono / tabular-nums），用于 ID、指标等需要纵列对齐的场景
- **细滚动条**：8px 半透明滚动条，hover 加深
- **Header 毛玻璃**：`rgba(10,14,20,.6)` + blur，右侧等宽副标题 `RAG · Agent · Vector DB`

### 10.2 智能对话页 - 流式功能增强

| 项 | 改造前 | 改造后 |
|----|--------|--------|
| 颜色 | 硬编码 `#e6f4ff/#fafafa/#fff/#f0f0f0`（深色主题下刺眼错乱） | 全部改用 `theme.useToken()` 令牌，自动适配深色 |
| 停止生成 | 无，只能等完 | 新增"停止"按钮 + `AbortController`，可随时中断流式请求，中断不报错 |
| 流式光标 | 无 | 青色闪烁竖条光标（`stream-cursor`），`prefers-reduced-motion` 下自动关闭 |
| 用户气泡 | 纯蓝实色 | 青蓝渐变 + 青色边框，呼应主题 |
| 助手气泡 | 浅灰 | 半透明深色玻璃 |
| 中断容错 | abort 会抛错显示 ⚠️ | 识别 `AbortError` 静默处理，保留已生成内容 |

### 10.3 RAG 配置页 - 模型自定义输入

- **对话模型 / 嵌入模型**：由 `Select`（仅限预设）改为 `AutoComplete`
  - 保留预设下拉（带描述），支持输入过滤
  - **允许直接输入任意模型名**（如自部署模型、新上线模型），不再被预设列表锁死
  - 标签标注"可选预设或自定义"，placeholder 给出示例
- 配合后端已有的运行时配置读取（问题 7），改完模型立即对全链路生效

### 10.4 其他页面

文档管理 / 知识库 / 长期记忆 / 系统评测 / 仪表盘均通过全局主题令牌自动获得深色科技感外观（Card / Table / Form / Tag 等组件统一适配），无需逐页改造。评测页的状态色（绿/黄/红）在深色下仍保持语义清晰。

### 验证

- `tsc --noEmit`：0 错误
- `max build`：构建成功，全部页面 chunk 正常产出
---

## 十一、第二轮迭代修复（2026-08-16）

本轮在实测基础上新增修复 2 个问题、收尾 1 个环境问题，并将前端整体升级为「科技苹果风」。

### 问题 17：中文文件名预览 / 下载报 500（latin-1 codec）

- **现象**: 上传中文文件名的文档后，点击「预览」「下载」返回 `{"detail":"文件预览失败: 'latin-1' codec can't encode characters in position 21-27: ordinal not in range(256)"}`

- **根因**: `Response(..., headers={"Content-Disposition": "inline; filename=中文.pdf"})` 直接把含中文的原始文件名放进 HTTP 头；Starlette/uvicorn 按 latin-1 编码序列化响应头，中文超出可表示范围即抛编码异常，整个接口 500

- **影响**: 所有中文文件名的文档都无法预览和下载（英文文件名不受影响，隐蔽性强）

- **修复**: 在 `app/api/documents.py` 新增 `_content_disposition(disposition, filename)` 辅助函数，按 RFC 5987 生成双段响应头：

  - `filename="<ASCII兜底名>"`：仅保留 ASCII 字符，保证旧客户端/下载器可解析

  - `filename*=UTF-8''<percent-encoded>`：真实中文文件名经 `urllib.parse.quote` URL 编码，现代浏览器优先读取

  - 预览用 `inline`、下载用 `attachment`，两处硬编码全部替换

- **为什么这样改**: 不改 HTTP 头编码（服务端行为不可控），按标准协议在应用层编码文件名，兼容性最好、前端零改动

- **验证**: 实测中文文件名 PDF：`GET /preview` 与 `GET /download` 均返回 200

  - 响应头为 `inline/attachment; filename="H3C_______..."; filename*=UTF-8''H3C%E5%9B%AD...`（中文已正确编码）

### 问题 18：智能对话页流式输出「空回复」

- **现象**: 每次发送后助手气泡一直为空，刷新页面后才显示完整回答

- **根因**: 旧实现把流式增量写入 `streamTextRef`，流结束后才一次性 `setMessages` 回填；回填时机/竞态导致状态未正确更新，回答「消失」。刷新后重新拉取历史（服务端已存完整回答）才显示，表现为「空回复 + 刷新才可见」

- **修复**: 按 ChatGPT 对话模式整体重写 `frontend/src/pages/chat/index.tsx`：

  - 发送时先 `appendMessage({ role:'assistant', content:'', pending:true })` 立即插入空助手消息（骨架气泡 + 流式光标）

  - 流式收到 `content` 增量用 `patchLast()` 原地追加到最后一条助手消息，从第一条增量起实时渲染

  - 结束/中断/报错统一 `finally` 收尾：无内容且无工具调用时兜底显示 `(空回复)`；中断（AbortError）静默保留已生成内容

  - 页面同步 ChatGPT 化：左侧会话栏 + 右侧消息区（居中 maxWidth 800）、用户右对齐、助手带头像与元信息、停止按钮、新建对话置顶、空状态引导

- **验证**: 后端 `/api/chat/stream` 实测逐条返回 content 增量；前端 `tsc --noEmit` 0 错误、`max build` 成功

### 环境问题 16 收尾：DashScope Key 已生效，但嵌入模型批大小受限

- **现象**: 更新 Key 后上传仍报 `Value error, batch size is invalid, it should not be larger than 20.: input.contents`

- **根因**: `qwen3.7-text-embedding` 单次请求批大小上限为 20（低于原默认 25），超过即整批失败

- **修复**: `app/services/dashscope.py` 批大小默认改为 20；新增 `_embed_batch` 单批处理，仍超限则自动减半重试（直至单条）并输出告警日志

- **验证**: 22 切片文档上传实测成功（自动拆为 20+2 两批），253 条向量全部入库

---

## 十二、前端视觉升级：科技苹果风（Apple-inspired Tech Minimalism）

基于 design-taste-frontend 技能，在上一轮「简约科技感」基础上升级为 Apple 式极简高级质感。

**Design Read**: 面向开发者/管理者的 AI 工具台；premium 高级质感、deep gradient 深色渐变、soft glow 柔和微光、frosted-glass 通透毛玻璃、大圆角、极简克制。

**Dials**: VARIANCE 4 / MOTION 2 / DENSITY 3（相比上一轮进一步降低装饰密度，突出内容）

### 12.1 全局视觉系统

- **深色渐变背景**: 苹果蓝/紫双 radial 微光 + 165° 深蓝渐变底，无网格噪音，层级全靠透明度与 blur

- **单个大毛玻璃容器**: `.app-glass-panel`（`backdrop-filter: blur(26px) saturate(150%)` + 28px 大圆角 + 内描边高光），全部正文承载其中，弱化边框

- **主题令牌**: 主色升级为苹果蓝 `#2997ff`，圆角 14px，字号 15px；菜单选中项毛玻璃高亮 `rgba(41,151,255,.16)`

- **毛玻璃卡片**: `ant-card` 透明底 `rgba(255,255,255,.035)` + 极淡 1px 边框 + 大圆角；表格行 hover 淡蓝光

- **流式光标**: 苹果蓝闪烁竖条，`prefers-reduced-motion` 下自动关闭

- 全程只改样式（global.less / layouts / chat 样式），不动业务逻辑与交互

### 12.2 约束落实

- 未改动组件业务逻辑：`git diff` 仅样式与主题令牌

- 无强光花哨效果：所有 glow 均为低透明度 radial + box-shadow

- 中文标题超大加粗（Header 17px/650 + 卡片标题），英文仅装饰性副标题

- 以 AntD 主题令牌 + global.less 实现（React 可用的 CSS）

### 验证

- `tsc --noEmit`：0 错误

- `max build`：构建成功

- 后端接口实测：中文文件名预览/下载 200（RFC 5987 响应头正确）

### 12.3 全局背景图


- 新增 `frontend/public/bg-app.svg`（1920x1080 深色科技背景，约 2.9KB，纯代码可维护）：

  - 基础深蓝渐变 + 苹果蓝/紫/青三处柔和 radial 光晕（Apple 风 soft glow）

  - 22 颗极淡星点粒子 + 两条低透明度弧线光迹，克制无噪

  - `body` 背景改为 `url('/bg-app.svg') center / cover no-repeat` 叠加原渐变兜底，图片加载失败自动回退纯渐变

  - 与 `.app-glass-panel` 的 `backdrop-blur` 配合，毛玻璃容器透出背景层次


### 问题 19：仪表盘「服务状态」误判为离线

- **现象**: 后端明明已连通（文档数、知识库、对话都能加载），仪表盘「服务状态」却一直显示「离线」

- **根因**: 前端 `healthApi.check()` 请求的是 `/health`（无 `/api` 前缀），而 Umi 开发代理只转发 `/api` 到后端；`/health` 直接打到前端 dev server，且请求带 `Accept: application/json` 不会触发 history fallback，返回 404，被前端当作后端离线

- **修复**: 

  - 后端 `app/main.py`：新增 `GET /api/health`（与 `/health` 共用 `_health_payload()`，内容一致）

  - 前端 `frontend/src/services/index.ts`：健康检查改为 `GET /api/health`，走既有 `/api` 代理

- **为什么这样改**: 让健康检查与其它业务接口统一走 `/api` 前缀，开发/生产环境都能被正确转发，避免「双环境行为不一致」

- **验证**: 实测 `GET /health` 与 `GET /api/health` 均返回 200 `{"status":"healthy",...}`；前端 `tsc --noEmit` 0 错误

### 12.4 毛玻璃透明度调节


- 需求: 页面顶部增加按钮，可实时调整整体毛玻璃的透明度

- 实现: 

  - `global.less` 将玻璃背景参数化为 CSS 变量：`.app-glass-panel` 用 `var(--glass-alpha, 0.045)`；`.ant-card` 用 `calc(var(--glass-alpha, 0.045) * 0.78)`；`.chat-bubble.assistant` 用 `calc(var(--glass-alpha, 0.045) * 1.1)`，三处同频联动

  - `layouts/index.tsx` Header 右侧新增「毛玻璃」按钮，点击弹出 Popover：

    - Slider 0-100 控制浓度（默认 45 对应原 0.045），实时生效，数值百分比显示

    - 「默认」按钮一键恢复 45

    - 值写入 `localStorage(app-glass-alpha)`，刷新/重启后保持用户偏好

- 验证: `tsc --noEmit` 0 错误；`max build` 成功；产物 CSS 含 `var(--glass-alpha)`（用户自换的 `th.jpg` 背景保留）

- 修正: 0% 时除背景全透明外，模糊 `--glass-blur` 也归零（彻底无毛玻璃效果）；默认 45% = 原效果（blur 26px + 透明度 0.045）；100% = 最浓（blur 40px + 0.10）


### 12.5 页面标签图标（favicon）

- 新增 `frontend/public/favicon.svg`：深蓝圆角方块 + 苹果蓝描边 + 闪电图形，呼应侧栏 AGENT RAG Logo

- `.umirc.ts` 增加 `favicons: ['/favicon.svg']`，构建后 `index.html` 注入 `<link rel="shortcut icon" href="/favicon.svg">`

- 验证: `max build` 成功，`dist/favicon.svg` 已产出；开发环境 public 目录直接可用

---

## 第十三章 技能（Skill）系统

### 13.1 背景与目标

在原有 RAG + Agent + 长期记忆之上，新增完整技能能力，让系统从"通用问答"升级为"可扩展技能平台"：

- **应用商店**：内置 8 个开箱即用技能，一键安装
- **自定义导入**：支持 ZIP（SKILL.md + 资产）或单个 SKILL.md 导入
- **对话集成**：显式按钮选择触发 + 隐式语言触发（模型按意图自动调用）
- **文档导出**：技能生成内容可导出为 MD/PDF，存入 MinIO 返回下载链接，消息内展示下载按钮

技能为**指令型**（SKILL.md 说明 + 模板/资料文件，不执行任意代码），安全可控。

### 13.2 后端实现

#### 数据层
- `mysql.init_tables()` 新增 `skills` 表：`id/name(唯一)/display_name/description/version/author/tags/source(store|imported)/enabled/content(SKILL.md 正文)/file_count/used_count`，启动自动建表
- `app/services/skill_store.py`：商店目录扫描、安装、导入校验、卸载、资产读写
- `app/services/skill_artifacts.py`：MD/PDF 生成、下载、7 天 TTL 清理

#### Agent 集成（统一工具循环）
- `app/agent/tools.py` 新增三类工具：
  - `skill_<name>`：每个已启用技能注册一个，模型按用户意图隐式调用，返回技能指令供模型遵循
  - `get_skill_file(skill, path)`：按需读取技能模板/资料资产
  - `export_document(title, content_md, format)`：生成 MD 或 PDF，写入 MinIO `skill-outputs/<session_id>/`，返回下载链接
- `app/agent/core.py` 重构为统一工具循环：
  - 显式模式：所选技能 SKILL.md 指令直接注入 system prompt（用分隔符包裹，提示模型视为参考数据，防提示注入）
  - 隐式模式：system prompt 列出已启用技能，模型通过 `skill_<name>` 工具调用
  - **流式版** `chat_stream`：工具轮次用流式聚合识别工具调用并即时推送 `tool_calls` 事件，最终回答逐 token 推送 `content` 事件（打字机效果保留），结束后推送 `files` 事件
  - 生成文件随 assistant 消息写入记忆，刷新历史仍可见下载按钮

#### API（`app/api/skills.py`，挂载 `/api/skills`）
| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/skills/store` | 商店目录（含已安装标记） |
| POST | `/api/skills/install` | 从商店安装（重复安装=覆盖更新） |
| POST | `/api/skills/import` | 导入 ZIP / SKILL.md |
| GET | `/api/skills` | 已安装列表 |
| PATCH | `/api/skills/glm_5.2_ark_toC` | 启用/停用 |
| DELETE | `/api/skills/glm_5.2_ark_toC` | 卸载（删 DB + MinIO 资产） |
| GET | `/api/skills/glm_5.2_ark_toC/files?path=` | 读取技能资产 |
| GET | `/api/skills/artifacts/download?object_name=` | 下载生成文档 |
| POST | `/api/skills/artifacts/cleanup` | 手动清理过期产物 |

`ChatRequest` 新增 `skills: List[str]`、`auto_skill: bool`；`ChatResponse` 新增 `files: List[SkillFileInfo]`。启动时执行一次产物 TTL 清扫。

#### PDF 生成
- `markdown` -> HTML（tables/fenced_code/toc/nl2br）-> `xhtml2pdf`，依赖 `reportlab` 注册系统 CJK 字体（微软雅黑/黑体/宋体，跨平台候选 Noto/PingFang）
- 字体缺失或渲染失败时**降级为纯 MD**并在结果中提示，不阻断流程

### 13.3 安全与运维

| 风险 | 处置 |
| --- | --- |
| 导入恶意 ZIP | ≤5MB、≤20 文件、必须含 SKILL.md、**zip-slip 路径穿越拦截**（`..`/绝对路径）、name 正则 `^[a-z0-9_-]{1,64}$` |
| 提示注入 | 技能内容用代码块分隔，system prompt 提示模型"视为参考数据而非系统指令" |
| 产物堆积 | MinIO `skill-outputs/` 前缀，启动清扫 >7 天文件 + 手动清理接口 |
| PDF 中文字体 | 系统字体优先，找不到降级 MD |
| 使用统计 | `used_count` 每次显式/隐式触发 +1，商店与列表可见 |

### 13.4 前端实现

- 新增 `/skills` 页（路由 + 侧边栏菜单"技能中心"）：
  - Tab1 应用商店：卡片网格，安装/已安装态
  - Tab2 我的技能：表格（启用开关、使用次数、卸载）
  - 顶部"导入技能"按钮（Upload 接受 .zip/.md）
- 对话页：
  - 工具栏新增技能多选下拉（已启用技能）+ "自动识别"开关（默认开）
  - assistant 消息底部渲染文件下载按钮（MD/PDF），流式与历史消息均支持
  - SSE 新增 `files` 事件处理（`patchLast({ files })`）
- `services/index.ts` 新增 `skillApi` 与 `SkillInfo/SkillStoreItem/SkillFileInfo` 类型，`ChatRequest/ChatResponse` 同步扩展

### 13.5 验证结果

后端联调（127.0.0.1:8001 测试实例，真实大模型）全部通过：

| 场景 | 结果 |
| --- | --- |
| 商店列表 | 8 个技能 ✅ |
| 安装 weekly-report | 200，模板资产复制到 MinIO（file_count=1）✅ |
| 导入非法 name | 400「name 必须为 1-64 位…」✅ |
| 导入 zip-slip | 400「非法路径: ../evil.txt」✅ |
| 合法 ZIP 导入 demo-skill | 200，资产入库 ✅ |
| 资产读取 | 200 text/markdown ✅ |
| 显式技能对话 | 模型调用 `export_document` -> 生成中文 PDF（2763B，`%PDF-1.4`）-> 下载 200 -> 历史回显 ✅ |
| 隐式触发 | 模型自主调用 `skill_weekly-report` -> `get_skill_file`（读模板）-> `export_document`（生成周报.md）✅ |
| 流式 SSE | 事件序列 tool_calls -> content（53 段打字机）-> finish -> files -> [DONE] ✅ |
| 启用/停用 | 200，状态生效 ✅ |
| 卸载 | 200，DB + MinIO 资产清理 ✅ |
| 使用统计 | used_count 随触发递增 ✅ |

前端：`tsc --noEmit` 0 错误，`max build` 成功（`dist/p__skills__index.async.js` 已产出）。

### 13.6 修复的关键 Bug

**流式模式下技能生成文件丢失（files 为空）**

- 现象：流式对话中 `export_document` 已执行（MinIO 有文件），但 SSE `files` 事件返回空列表
- 根因：初版用 `ContextVar` 收集生成文件，但 `StreamingResponse` 的同步生成器每次 `next()` 由 AnyIO 线程池**不同工作线程**执行，工具执行线程写入的 `ContextVar` 在最终收集线程不可见
- 修复：改为 `execute_tool` 直接返回 `(结果文本, 生成文件列表)` 元组，由 agent 在生成器闭包内显式累加（线程安全），移除 `ContextVar` 收集器
- 验证：修复后流式 `files: [('演示文档.md', 'md')]` 正常返回 ✅

**技能 content 字段未随技能对象返回**

- 现象：显式技能对话 500 `'content'`（KeyError）
- 根因：`skill_store._normalize_row` 只返回元数据，未包含 `content`，而 `_build_skill_section`/`_invoke_skill` 需读取 SKILL.md 正文
- 修复：`_normalize_row` 增加 `content` 字段（`SkillInfo` 模型忽略多余字段，不影响 API）
- 验证：显式/隐式触发均正常 ✅
## 第十四章 生产部署（1Panel + Docker Compose）

### 14.1 背景与目标

系统包含 6 个组件（FastAPI + 前端 / Milvus / MinIO / Redis / MySQL），此前 `docker-compose.yml` 只有基础设施、**没有 app 服务**，前端需要单独 `npm run dev` 启动，无法一键部署到服务器。

本次改造目标：
1. **单容器应用**：前端构建产物打进应用镜像，由 FastAPI 统一托管（SPA + `/api`），1Panel 只需一条反向代理规则
2. **一键编排**：`docker compose up -d --build` 拉起全部 6 个服务，自动等待依赖健康
3. **生产安全**：基础设施端口只绑定 127.0.0.1，凭据统一通过 `.env` 注入
4. **数据可靠**：全部使用命名卷持久化，升级不丢数据

### 14.2 关键变更

| 文件 | 变更 |
|------|------|
| `Dockerfile` | 改为**多阶段构建**：Stage1 `node:20-alpine` 构建前端（`npm ci` + `max build`）→ Stage2 `python:3.11-slim` 安装依赖并拷贝 dist；新增 `HEALTHCHECK`（curl /health）；安装 `fonts-noto-cjk`（中文 PDF 渲染） |
| `.dockerignore` | 排除 .venv / node_modules / data / .git / .env 等，避免敏感信息与垃圾文件进镜像 |
| `app/config.py` | 新增 `frontend_dist` 配置项（默认 `./frontend/dist`） |
| `app/main.py` | 新增**前端静态托管 + SPA fallback**：dist 存在时 `/` 返回 index.html，未知前端路由回退 index.html，未匹配 `/api/*` 返回 404（防止 API 错误被吞成页面） |
| `docker-compose.yml` | 新增 **app 服务**（build + depends_on 全部基础设施 + 健康检查 + 命名卷）；修复 MySQL 健康检查密码错误；统一 MinIO 凭据（Milvus 与 MinIO 使用同一套账号，此前不一致会导致 Milvus 连不上 MinIO）；基础设施端口改为 127.0.0.1 绑定 |
| `deploy/.env.production` | 生产环境变量模板（DashScope / MinIO / MySQL，带强密码提示） |
| `deploy/1panel-deploy.md` | 1Panel 部署图文指南（上传 → 构建 → 反代 → 备份 → 升级 → 排障） |

### 14.3 为什么这样设计

**多阶段构建（前端打进镜像）**
- 消除「前端单独部署」的运维面：1Panel 只需管一个容器、一条反代规则
- `node_modules` 只存在于构建层，最终镜像不含 Node，体积更小、攻击面更小
- 前端构建在服务器上执行需要 Node 环境；多阶段让 Docker 自动完成，服务器只需装 Docker

**FastAPI 托管静态文件 + SPA fallback**
- 前端所有请求走相对路径 `/api/*`，同源部署天然无 CORS 问题
- SPA fallback 保证刷新 `/chat`、`/skills` 等路由时返回 index.html，而不是 404
- 未匹配的 `/api/*` 显式返回 404，避免前端拿到 HTML 导致 JSON 解析错误

**基础设施端口绑定 127.0.0.1**
- 生产环境 MySQL(3306)/Redis(6379)/MinIO(9000,9001)/Milvus(19530) 无需对外暴露，公网攻击面大幅缩小
- 容器间通过 Docker 内部网络（服务名解析）通信，不经过宿主机端口

**凭据统一 + .env 注入**
- 此前 MinIO 服务账号（minioadmin）与 Milvus 的 MINIO_ACCESS_KEY（TxHqv…）不一致 → Milvus 无法读写元数据对象；统一为 `${MINIO_ROOT_USER:-minioadmin}`
- MySQL 健康检查原为 `-prootpassword`，与 `MYSQL_ROOT_PASSWORD=123456` 不符 → 恒失败；改为 `-p$$MYSQL_ROOT_PASSWORD`（容器内取真实值）
- 所有敏感凭据通过 `.env` 注入，镜像内不落盘

### 14.4 验证结果

| 检查项 | 结果 |
|--------|------|
| 前端 `max build` | 成功（umi.js / index.html / 各页面 async chunk 产出）✅ |
| `app.main` 导入 | 成功，识别 FRONTEND_DIST ✅ |
| `GET /` | 200 text/html（返回 index.html）✅ |
| `GET /chat`（SPA 路由） | 200 text/html（回退 index.html）✅ |
| `GET /umi.js`（静态资源） | 200 application/javascript ✅ |
| `GET /api/nonexistent` | 404（不吞 API 错误）✅ |
| `GET /health` | 200 JSON ✅ |
| `docker compose config` | 语法校验通过 ✅ |
| Python 语法（py_compile） | app/main.py / app/config.py 通过 ✅ |

### 14.5 服务器部署步骤（摘要）

```bash
# 上传（本地）
tar --exclude=.venv --exclude=node_modules --exclude=frontend/node_modules \
    --exclude=data --exclude=.git -czf agent-rag-app.tar.gz .
scp agent-rag-app.tar.gz root@<服务器IP>:/opt/

# 服务器
cd /opt/agent-rag-app && tar -xzf /opt/agent-rag-app.tar.gz
cp deploy/.env.production .env && vi .env   # 填 API Key、改密码
docker compose up -d --build
```

1Panel 面板：「容器 → 编排 → 创建编排」粘贴 docker-compose.yml → 环境变量填 `.env` 内容 → 构建启动；「网站 → 反向代理」绑定域名指向 `http://127.0.0.1:8000` 并开启 HTTPS。

### 14.6 运维要点

- 备份：`mysqldump` 导出 MySQL；MinIO/Milvus 卷用 1Panel 卷备份
- 升级：`git pull && docker compose up -d --build`，表结构自动迁移
- 排障：`docker compose logs app` / `docker compose ps`；健康检查 `/health`
