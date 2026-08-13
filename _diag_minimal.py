"""精简诊断: 直接检查路由 + OpenAPI 生成"""
import sys, os, traceback

sys.path.insert(0, r'C:\Users\KK\WorkBuddy\Agent\agent-rag-app')
os.chdir(r'C:\Users\KK\WorkBuddy\Agent\agent-rag-app')

# 先单独测试 models 导入
try:
    from app.models import schemas
    print("=== Schemas 导入成功 ===")
    print(f"  DocumentProcessResult fields: {list(schemas.DocumentProcessResult.model_fields.keys())}")
    print(f"  DocumentInfo fields: {list(schemas.DocumentInfo.model_fields.keys())}")
except Exception as e:
    print("=== Schemas 导入失败 ===")
    traceback.print_exc()
    sys.exit(1)

# 尝试单独构造 FastAPI app 测试路由定义
try:
    from fastapi import FastAPI
    from fastapi import APIRouter, UploadFile, File
    from app.models.schemas import DocumentProcessResult, DocumentListResponse, DocumentInfo, DocumentDeleteResponse

    # 构造类似 documents.py 的路由
    test_router = APIRouter()

    @test_router.post("/upload", response_model=DocumentProcessResult)
    async def upload(file: UploadFile = File(...)):
        return None

    @test_router.get("", response_model=DocumentListResponse)
    async def list_docs():
        return None

    @test_router.get("/{doc_id}", response_model=DocumentInfo)
    async def get_doc(doc_id: str):
        return None

    @test_router.get("/{doc_id}/download")
    async def download(doc_id: str):
        return None

    @test_router.delete("/{doc_id}", response_model=DocumentDeleteResponse)
    async def delete_doc(doc_id: str):
        return None

    app2 = FastAPI()
    app2.include_router(test_router, prefix="/api/documents")

    schema = app2.openapi()
    print(f"=== 测试路由 OpenAPI 生成成功, 路径: {list(schema.get('paths', {}).keys())} ===")

except Exception as e:
    print("=== 测试路由 OpenAPI 生成失败 ===")
    traceback.print_exc()