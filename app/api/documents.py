"""
文档管理接口
- POST   /api/documents/upload          上传文档(MD5去重 + 自动入库)
- GET    /api/documents                 列出所有文档(从数据库)
- GET    /api/documents/{doc_id}        查询单个文档详情
- GET    /api/documents/{doc_id}/download  下载文档
- GET    /api/documents/{doc_id}/preview  在线预览文档
- DELETE /api/documents/{doc_id}        删除文档(MinIO + Milvus + DB 联动)
"""
import os
import uuid
import hashlib

from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from fastapi.responses import Response
from loguru import logger

from app.models.schemas import (
    DocumentProcessResult,
    DocumentListResponse,
    DocumentInfo,
    DocumentDeleteResponse,
)
from app.services.minio import minio_service
from app.services.milvus import milvus_service
from app.services.database import db_service
from app.services.config_store import get_rag_config
from app.rag.loader import document_loader
from app.rag.splitter import text_splitter, llm_split_callback
from app.rag.embedder import embedder

router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".docx"}


async def _compute_md5(file:UploadFile) -> tuple[str, int]:
    """计算文件的 MD5"""
    md5_obj=hashlib.md5()
    total_size = 0
    chunk_size=65536
    # 1.异步分块读取文件
    while chunk:=await file.read(chunk_size):
        md5_obj.update(chunk)
        total_size+=len(chunk)
    await file.seek(0)
    return md5_obj.hexdigest(),total_size


@router.post("/upload", response_model=DocumentProcessResult, summary="上传文档(MD5去重)")
async def upload_document(
    file: UploadFile = File(...),
    split_method: str = Form(None, description="切片方式: recursive/fixed/semantic/structure/sentence/llm"),
):
    """
    上传文档完整流程:
    1. 计算 MD5, 查数据库去重 -> 已存在直接返回
    2. 文件保存到 MinIO
    3. 加载文档文本 -> 按指定方式切分 -> 向量化
    4. 存入 Milvus 向量库
    5. 元数据写入数据库

    split_method 不传时使用系统配置中的默认切片方式
    """
    filename = file.filename or "unknown"  #获取文件名
    ext = os.path.splitext(filename)[1].lower() #获取文件的格式

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {ext}, 支持: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    try:
        # 1.优化文件转MD5的计算(并且计算文件的大小)
        file_md5, file_size  =await _compute_md5(file)
        content_type = file.content_type or "application/octet-stream"

        # 2. 去重检查: 数据库中已存在相同 MD5 则跳过
        existing = db_service.get_by_md5(file_md5)
        if existing is not None:
            logger.info(f"文档已存在(MD5重复),跳过上传: {filename} -> {existing['doc_id']}")
            return DocumentProcessResult(
                doc_id=existing["doc_id"],
                filename=existing["filename"],
                object_name=existing["object_name"],
                md5=file_md5,
                file_size=existing["file_size"],
                char_count=existing["char_count"],
                chunk_count=existing["chunk_count"],
                vector_count=existing["vector_count"],
                duplicated=True,
                message=f"文档已存在,跳过上传 (原始文件: {existing['filename']})",
            )

        # 3. 上传到 MinIO(待优化,大文件切片上传)
        content=file.read()
        doc_id = str(uuid.uuid4())
        object_name = f"{doc_id}_{filename}"
        minio_service.upload_bytes(
            object_name=object_name,
            data=content,
            content_type=content_type,
        )

        # 4. 加载文档文本
        text = document_loader.load_bytes(content, ext)
        char_count = len(text)

        if not text.strip():
            # 内容为空,回滚 MinIO 文件
            minio_service.delete(object_name)
            raise HTTPException(status_code=400, detail="文档内容为空或无法解析")

        # 5. 文本切分(支持指定切片方式)
        config = get_rag_config()
        effective_method = split_method or config.get("split_method", "recursive")
        llm_fn = llm_split_callback if effective_method == "llm" else None
        chunks = text_splitter.split(text, method=effective_method, llm_split_fn=llm_fn)
        if not chunks:
            minio_service.delete(object_name)
            raise HTTPException(status_code=400, detail="文档切分后无有效内容")

        # 6. 向量化
        vectors = embedder.embed_documents(chunks)

        # 7. 存入 Milvus
        records = []
        for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
            records.append(
                {
                    "id": f"{doc_id}_{i}",
                    "vector": vector,
                    "text": chunk,
                    "doc_id": doc_id,
                    "source": filename,
                    "chunk_index": i,
                }
            )
        milvus_service.insert(records)

        # 8. 元数据写入数据库
        db_service.add_document(
            {
                "doc_id": doc_id,
                "filename": filename,
                "md5": file_md5,
                "object_name": object_name,
                "file_size": file_size,
                "content_type": content_type,
                "char_count": char_count,
                "chunk_count": len(chunks),
                "vector_count": len(vectors),
                "status": "active",
            }
        )

        logger.info(f"文档入库完成: {filename} -> {len(chunks)} 块 / {len(vectors)} 向量")

        return DocumentProcessResult(
            doc_id=doc_id,
            filename=filename,
            object_name=object_name,
            md5=file_md5,
            file_size=file_size,
            char_count=char_count,
            chunk_count=len(chunks),
            vector_count=len(vectors),
            duplicated=False,
            message="文档上传并入库成功",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"文档上传失败: {e}")
        raise HTTPException(status_code=500, detail=f"文档处理失败: {e}")


@router.get("", response_model=DocumentListResponse, summary="列出所有文档")
async def list_documents():
    """从数据库列出所有已上传文档的元数据"""
    docs = db_service.list_documents()
    return DocumentListResponse(
        total=len(docs),
        documents=[DocumentInfo(**d) for d in docs],
    )


@router.get("/{doc_id}", response_model=DocumentInfo, summary="查询单个文档详情")
async def get_document(doc_id: str):
    """按 doc_id 查询文档元数据"""
    doc = db_service.get_by_doc_id(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"文档不存在: {doc_id}")
    return DocumentInfo(**doc)


@router.get("/{doc_id}/download", summary="下载文档")
async def download_document(doc_id: str):
    """按 doc_id 下载文档文件(附件方式)"""
    doc = db_service.get_by_doc_id(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"文档不存在: {doc_id}")

    try:
        data = minio_service.download(doc["object_name"])
        filename = doc["filename"]
        return Response(
            content=data,
            media_type=doc.get("content_type") or "application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(data)),
            },
        )
    except Exception as e:
        logger.error(f"下载失败: {e}")
        raise HTTPException(status_code=404, detail=f"文件下载失败: {e}")


@router.get("/{doc_id}/preview", summary="在线预览文档")
async def preview_document(doc_id: str):
    """按 doc_id 在线预览文档(浏览器内联显示,适合 PDF/TXT/MD)"""
    doc = db_service.get_by_doc_id(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"文档不存在: {doc_id}")

    try:
        data = minio_service.download(doc["object_name"])
        filename = doc["filename"]
        return Response(
            content=data,
            media_type=doc.get("content_type") or "application/octet-stream",
            headers={
                "Content-Disposition": f'inline; filename="{filename}"',
                "Content-Length": str(len(data)),
            },
        )
    except Exception as e:
        logger.error(f"预览失败: {e}")
        raise HTTPException(status_code=404, detail=f"文件预览失败: {e}")


@router.delete("/{doc_id}", response_model=DocumentDeleteResponse, summary="删除文档")
async def delete_document(doc_id: str):
    """
    删除文档(三方联动):
    1. 从数据库删除元数据
    2. 从 MinIO 删除文件
    3. 从 Milvus 删除该文档的所有向量
    """
    doc = db_service.get_by_doc_id(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"文档不存在: {doc_id}")

    object_name = doc["object_name"]
    filename = doc["filename"]
    errors = []

    # 1. 删除 MinIO 文件
    try:
        minio_service.delete(object_name)
    except Exception as e:
        errors.append(f"MinIO: {e}")
        logger.warning(f"删除 MinIO 文件失败: {e}")

    # 2. 删除 Milvus 向量
    deleted_vectors = 0
    try:
        deleted_vectors = milvus_service.delete_by_doc_id(doc_id)
    except Exception as e:
        errors.append(f"Milvus: {e}")
        logger.warning(f"删除 Milvus 向量失败: {e}")

    # 3. 删除数据库记录
    db_service.delete_by_doc_id(doc_id)

    message = "文档已删除"
    if errors:
        message += f"(部分清理失败: {'; '.join(errors)})"

    logger.info(f"文档删除完成: {filename} ({doc_id}), 向量: {deleted_vectors}")
    return DocumentDeleteResponse(
        doc_id=doc_id,
        filename=filename,
        deleted_vectors=deleted_vectors,
        message=message,
    )
