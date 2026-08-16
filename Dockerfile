# ============================================================
# Agent RAG App - 生产镜像 (多阶段构建)
# Stage 1: Node 构建前端 (umi/max) -> dist
# Stage 2: Python 运行后端 + 托管前端静态文件
# 依赖基础设施 (Milvus/MinIO/Redis/MySQL) 由 docker-compose 编排
# ============================================================

# ---------- Stage 1: 前端构建 ----------
FROM node:20-alpine AS frontend-builder

WORKDIR /build
# 仅拷贝依赖清单, 利用 Docker 层缓存
COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN npm ci --no-audit --no-fund

# 拷贝源码并构建
COPY frontend/ ./
RUN npm run build

# ---------- Stage 2: Python 运行时 ----------
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# 系统依赖:
#   curl            - 容器健康检查
#   fonts-noto-cjk  - PDF 中文渲染 (xhtml2pdf/reportlab 系统字体)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖 (锁定版本)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码 + 内置技能商店 + 前端构建产物
COPY app/ ./app/
COPY skills_catalog/ ./skills_catalog/
COPY --from=frontend-builder /build/dist ./frontend/dist

# 运行期数据目录 (上传临时文件 / SQLite 回退)
RUN mkdir -p /app/data/uploads

EXPOSE 8000

# 健康检查: 命中 FastAPI /health
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=5 \
  CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
