"""
Milvus 向量数据库服务 (基于 MilvusClient API)
- 集合管理(创建/删除)
- 向量插入(按行)
- 向量检索
- 按文档ID删除

注: 使用 pymilvus 2.4+ 推荐的 MilvusClient API,
    替代将在 3.1 移除的 ORM 风格 Collection API。
"""
from typing import List, Dict, Any, Optional
from loguru import logger

from pymilvus import MilvusClient, DataType

from app.config import settings


class MilvusService:
    """Milvus 操作封装 (MilvusClient API)"""

    def __init__(self):
        self._client: Optional[MilvusClient] = None

    def _get_client(self) -> MilvusClient:
        """获取客户端(懒加载, 首次调用时建立连接)"""
        if self._client is None:
            uri = f"http://{settings.milvus_host}:{settings.milvus_port}"
            self._client = MilvusClient(uri=uri)
            logger.info(f"已连接 Milvus (MilvusClient): {uri}")
        return self._client

    def ensure_collection(self):
        """确保集合存在, 不存在则创建(含 schema + 索引)"""
        client = self._get_client()

        if client.has_collection(settings.milvus_collection):
            logger.info(f"集合已存在: {settings.milvus_collection}")
            return

        # 1. 定义 schema
        from app.services.config_store import get_rag_config
        dim = get_rag_config().get("embed_dim", settings.embed_dim)
        schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field(field_name="id", datatype=DataType.VARCHAR, max_length=64, is_primary=True)
        schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=dim)
        schema.add_field(field_name="text", datatype=DataType.VARCHAR, max_length=65535)
        schema.add_field(field_name="doc_id", datatype=DataType.VARCHAR, max_length=64)
        schema.add_field(field_name="source", datatype=DataType.VARCHAR, max_length=512)
        schema.add_field(field_name="chunk_index", datatype=DataType.INT64)

        # 2. 准备索引参数(读取运行时配置: 索引类型/距离度量/nlist)
        from app.services.config_store import get_rag_config
        config = get_rag_config()
        index_params = MilvusClient.prepare_index_params()
        index_params.add_index(
            field_name="vector",
            index_type=config.get("index_type", "IVF_FLAT"),
            metric_type=config.get("search_metric", "COSINE"),
            params={"nlist": config.get("nlist", 128)},
        )

        # 3. 创建集合(同时建立索引, MilvusClient 自动 load)
        client.create_collection(
            collection_name=settings.milvus_collection,
            schema=schema,
            index_params=index_params,
        )
        logger.info(f"集合创建成功: {settings.milvus_collection}")

    def drop_collection(self):
        """删除集合"""
        client = self._get_client()
        if client.has_collection(settings.milvus_collection):
            client.drop_collection(settings.milvus_collection)
            logger.info(f"集合已删除: {settings.milvus_collection}")

    def insert(self, records: List[Dict[str, Any]]) -> List[str]:
        """
        批量插入向量(按行)
        records: [{"id", "vector", "text", "doc_id", "source", "chunk_index"}]
        Returns: 插入的 id 列表
        """
        if not records:
            return []

        client = self._get_client()
        # MilvusClient 按行插入(字典列表)
        data = [
            {
                "id": r["id"],
                "vector": r["vector"],
                "text": r["text"],
                "doc_id": r["doc_id"],
                "source": r.get("source", ""),
                "chunk_index": r.get("chunk_index", 0),
            }
            for r in records
        ]
        result = client.insert(
            collection_name=settings.milvus_collection, data=data
        )

        # 兼容不同版本返回: dict 或 MutationResult
        if isinstance(result, dict):
            ids = result.get("ids", []) or result.get("primary_keys", [])
        else:
            ids = getattr(result, "primary_keys", []) or getattr(result, "ids", [])

        logger.info(f"插入 {len(records)} 条向量")
        return [str(i) for i in ids]

    def search(
        self, query_vector: List[float], top_k: int = 4
    ) -> List[Dict[str, Any]]:
        """
        向量检索
        Returns: [{"id", "score", "text", "doc_id", "source", "chunk_index"}]
        """
        from app.services.config_store import get_rag_config
        config = get_rag_config()
        metric = config.get("search_metric", "COSINE")
        # nprobe 仅对 IVF 系列索引有意义; HNSW 用 ef, FLAT 无需参数
        index_type = config.get("index_type", "IVF_FLAT")
        if index_type.startswith("IVF"):
            search_params = {"metric_type": metric, "params": {"nprobe": config.get("nprobe", 16)}}
        elif index_type == "HNSW":
            search_params = {"metric_type": metric, "params": {"ef": max(config.get("nprobe", 16) * 4, 32)}}
        else:
            search_params = {"metric_type": metric}

        client = self._get_client()
        results = client.search(
            collection_name=settings.milvus_collection,
            data=[query_vector],
            anns_field="vector",
            limit=top_k,
            search_params=search_params,
            output_fields=["text", "doc_id", "source", "chunk_index"],
        )

        # MilvusClient.search 返回 list[list[dict]], 每个命中是 dict:
        # {"id":..., "distance":..., "entity": {"text":..., ...}}
        hits = []
        for hit in results[0]:
            if isinstance(hit, dict):
                entity = hit.get("entity", {}) or {}
                hits.append(
                    {
                        "id": hit.get("id"),
                        "score": float(hit.get("distance", 0)),
                        "text": entity.get("text"),
                        "doc_id": entity.get("doc_id"),
                        "source": entity.get("source"),
                        "chunk_index": entity.get("chunk_index"),
                    }
                )
            else:
                # 兼容旧式 Hit 对象(理论上不会走到)
                entity = hit.entity or {}
                hits.append(
                    {
                        "id": getattr(hit, "id", None),
                        "score": float(getattr(hit, "distance", getattr(hit, "score", 0))),
                        "text": entity.get("text"),
                        "doc_id": entity.get("doc_id"),
                        "source": entity.get("source"),
                        "chunk_index": entity.get("chunk_index"),
                    }
                )
        return hits

    def delete_by_doc_id(self, doc_id: str) -> int:
        """
        按文档ID删除该文档所有向量
        Returns: 实际删除数量(先查询计数)
        """
        client = self._get_client()
        expr = f'doc_id == "{doc_id}"'

        # 先查询统计该文档的向量数量(MilvusClient.delete 不返回删除数)
        try:
            query_result = client.query(
                collection_name=settings.milvus_collection,
                filter=expr,
                output_fields=["id"],
                limit=16384,
            )
            count = len(query_result) if isinstance(query_result, list) else 0
        except Exception as e:
            logger.warning(f"查询删除数量失败, 继续删除: {e}")
            count = 0

        client.delete(collection_name=settings.milvus_collection, filter=expr)
        logger.info(f"删除文档 {doc_id} 的向量, 预计 {count} 条")
        return count

    def stats(self) -> Dict[str, Any]:
        """集合统计"""
        client = self._get_client()
        try:
            stat = client.get_collection_stats(
                collection_name=settings.milvus_collection
            )
            # 返回 dict: {"row_count": N}
            row_count = (
                stat.get("row_count", 0) if isinstance(stat, dict) else 0
            )
        except Exception as e:
            logger.warning(f"获取统计失败: {e}")
            row_count = 0

        return {
            "collection": settings.milvus_collection,
            "num_entities": int(row_count),
        }


# 单例
milvus_service = MilvusService()
