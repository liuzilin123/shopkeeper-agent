"""
指标元数据 ES 仓储

为指标元数据建立 Elasticsearch 全文索引，作为指标召回里的稀疏检索通道
和 Qdrant 向量召回互补，提升对指标名 别名 描述中关键词的召回率
"""

from dataclasses import asdict

from elasticsearch import AsyncElasticsearch

from app.entities.metric_info import MetricInfo


class MetricESRepository:
    """负责指标元数据全文索引的创建 写入和关键词检索"""

    index_name = "metric_index"
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
        },
    }

    def __init__(self, client: AsyncElasticsearch):
        self.client = client

    async def ensure_index(self):
        """确保指标元数据全文索引已经创建好"""
        if not await self.client.indices.exists(index=self.index_name):
            await self.client.indices.create(
                index=self.index_name, mappings=self.index_mappings
            )

    async def index(self, metric_infos: list[MetricInfo], batch_size: int = 20):
        """分批写入指标元数据，用 MetricInfo.id 作为文档 id 保证幂等覆盖"""
        if not metric_infos:
            return

        for i in range(0, len(metric_infos), batch_size):
            batch = metric_infos[i : i + batch_size]
            operations = []
            for metric_info in batch:
                operations.append(
                    {"index": {"_index": self.index_name, "_id": metric_info.id}}
                )
                operations.append(asdict(metric_info))
            await self.client.bulk(operations=operations)

    async def search(
        self, keyword: str, score_threshold: float = 0.5, limit: int = 20
    ) -> list[MetricInfo]:
        """按关键词跨指标名 描述 别名做全文检索，并还原为 MetricInfo 实体"""
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
        return [MetricInfo(**hit["_source"]) for hit in resp["hits"]["hits"]]
