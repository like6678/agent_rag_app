"""诊断: 导入所有 API 路由 + 生成 OpenAPI"""
import sys, os, traceback

sys.path.insert(0, r'C:\Users\KK\WorkBuddy\Agent\agent-rag-app')
os.chdir(r'C:\Users\KK\WorkBuddy\Agent\agent-rag-app')

# 单独测试 chat.py 路由
try:
    from fastapi import FastAPI, APIRouter
    from app.api.chat import router as chat_router
    from app.api.knowledge_base import router as kb_router
    print(f"=== chat.py 路由加载成功 ===")
    for r in chat_router.routes:
        print(f"  {list(r.methods)} {r.path}")
    print(f"=== knowledge_base.py 路由加载成功 ===")
    for r in kb_router.routes:
        print(f"  {list(r.methods)} {r.path}")

    # 尝试导入 documents (可能触发 milvus/minio 等)
    try:
        from app.api.documents import router as docs_router
        print(f"=== documents.py 路由加载成功 ===")
        for r in docs_router.routes:
            print(f"  {list(r.methods)} {r.path}")
    except Exception as e:
        print(f"=== documents.py 加载失败: {e} ===")
        traceback.print_exc()
except Exception as e:
    print("=== 路由加载失败 ===")
    traceback.print_exc()