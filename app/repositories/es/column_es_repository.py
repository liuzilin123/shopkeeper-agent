"""
字段元数据 ES 仓储

为字段元数据建立 Elasticsearch 全文索引，作为字段召回里的稀疏检索通道
和 Qdrant 向量召回互补，提升对精确词（字段名 别名 描述中的关键词）的召回率
"""

from dataclasses import asdict

from elasticsearch import AsyncElasticsearch

from app.entities.column_info import ColumnInfo


class ColumnESRepository:
    """负责字段元数据全文索引的创建 写入和关键词检索"""

    index_name = "column_index"
    # name 和 alias 是字段最关键的检索入口，description 次之，通过权重提升匹配质量
    index_mappings = {
        "dynamic": False,
        "properties": {
            "id": {"type": "keyword"},
            "name": {
                "type": "text",
                "analyzer": "ik_max_word",
                "search_analyzer": "ik_max_word",
            },
            "description": {
                "type": "text",
                "analyzer": "ik_max_word",
                "search_analyzer": "ik_max_word",
            },
            "alias": {
                "type": "text",
                "analyzer": "ik_max_word",
                "search_analyzer": "ik_max_word",
            },
            "table_id": {"type": "keyword"},
            "role": {"type": "keyword"},
        },
    }

    def __init__(self, client: AsyncElasticsearch):
        self.client = client

    async def ensure_index(self):
        """确保字段元数据全文索引已经创建好"""
        if not await self.client.indices.exists(index=self.index_name):
            await self.client.indices.create(
                index=self.index_name, mappings=self.index_mappings
            )

    async def index(self, column_infos: list[ColumnInfo], batch_size: int = 20):
        """分批写入字段元数据，用 ColumnInfo.id 作为文档 id 保证幂等覆盖"""
        if not column_infos:
            return

        for i in range(0, len(column_infos), batch_size):
            batch = column_infos[i : i + batch_size]
            operations = []
            for column_info in batch:
                operations.append(
                    {"index": {"_index": self.index_name, "_id": column_info.id}}
                )
                operations.append(asdict(column_info))
            await self.client.bulk(operations=operations)

    async def search(
        self, keyword: str, score_threshold: float = 0.5, limit: int = 20
    ) -> list[ColumnInfo]:
        """按关键词跨字段名 描述 别名做全文检索，并还原为 ColumnInfo 实体"""
        resp = await self.client.search(
            index=self.index_name,
            query={
                "multi_match": {
                    "query": keyword,
                    "fields": ["name^3", "description", "alias^2"],
                }
            },
            size=limit,
            min_score=score_threshold,
        )
        # _source 里保存的是完整 ColumnInfo 字段结构，业务层继续使用实体对象
        return [ColumnInfo(**hit["_source"]) for hit in resp["hits"]["hits"]]
