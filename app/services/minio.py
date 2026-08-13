"""
MinIO 文件存储服务
- bucket 管理
- 文件上传 / 下载 / 删除
"""
import io
from typing import Optional, BinaryIO
from loguru import logger

from minio import Minio
from minio.error import S3Error

from app.config import settings


class MinIOService:
    """MinIO 对象存储封装"""

    def __init__(self):
        self._client: Optional[Minio] = None

    def get_client(self) -> Minio:
        if self._client is None:
            self._client = Minio(
                settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure,
            )
        return self._client

    def ensure_bucket(self):
        """确保 bucket 存在"""
        client = self.get_client()
        if not client.bucket_exists(settings.minio_bucket):
            client.make_bucket(settings.minio_bucket)
            logger.info(f"创建 bucket: {settings.minio_bucket}")

    def upload_bytes(self, object_name: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        """
        上传字节数据
        返回 object_name
        """
        self.ensure_bucket()
        client = self.get_client()
        client.put_object(
            bucket_name=settings.minio_bucket,
            object_name=object_name,
            data=io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        logger.info(f"上传文件: {object_name} ({len(data)} bytes)")
        return object_name

    def upload_fileobj(self, object_name: str, fileobj: BinaryIO, length: int, content_type: str = "application/octet-stream") -> str:
        """上传文件对象"""
        self.ensure_bucket()
        client = self.get_client()
        client.put_object(
            bucket_name=settings.minio_bucket,
            object_name=object_name,
            data=fileobj,
            length=length,
            content_type=content_type,
        )
        logger.info(f"上传文件: {object_name} ({length} bytes)")
        return object_name

    def download(self, object_name: str) -> bytes:
        """下载文件为字节"""
        client = self.get_client()
        response = client.get_object(settings.minio_bucket, object_name)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def delete(self, object_name: str):
        """删除文件"""
        client = self.get_client()
        client.remove_object(settings.minio_bucket, object_name)
        logger.info(f"删除文件: {object_name}")

    def list_objects(self, prefix: str = "") -> list:
        """列出对象"""
        client = self.get_client()
        objects = client.list_objects(settings.minio_bucket, prefix=prefix, recursive=True)
        return [
            {"name": obj.object_name, "size": obj.size, "last_modified": str(obj.last_modified)}
            for obj in objects
        ]


# 单例
minio_service = MinIOService()
