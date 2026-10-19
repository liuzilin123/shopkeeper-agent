"""
电商问数 Agent 运行上下文

Context 用来保存一次图执行过程中不参与状态合并的外部依赖或配置
本章放入多路召回需要的 Embedding 客户端 Qdrant 仓储和 ES 仓储
召回信息合并阶段还会访问 Meta MySQL，用于按 id 补齐字段和表结构元数据
额外上下文补全阶段会访问 DW MySQL，用于读取数据库方言和版本
这样节点可以通过 runtime.context 复用外部工具，而不需要把连接类对象塞进 State
"""

from typing import TypedDict

from langchain_huggingface import HuggingFaceEndpointEmbeddings

from app.agent.reranker import Reranker
from app.repositories.es.column_es_repository import ColumnESRepository
from app.repositories.es.metric_es_repository import MetricESRepository
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository


class DataAgentContext(TypedDict):
    """LangGraph Runtime 中传递的上下文对象"""

    # 字段向量仓储，负责根据向量从 Qdrant 检索候选字段
    column_qdrant_repository: ColumnQdrantRepository
    # 字段全文仓储，负责从 Elasticsearch 检索字段元数据，作为稀疏召回通道
    column_es_repository: ColumnESRepository
    # Embedding 客户端，负责把关键词转换成向量检索所需的 query vector
    embedding_client: HuggingFaceEndpointEmbeddings
    # 指标向量仓储，负责根据向量从 Qdrant 检索候选指标
    metric_qdrant_repository: MetricQdrantRepository
    # 指标全文仓储，负责从 Elasticsearch 检索指标元数据，作为稀疏召回通道
    metric_es_repository: MetricESRepository
    # 字段取值全文检索仓储，负责从 Elasticsearch 检索真实字段值
    value_es_repository: ValueESRepository
    # 重排器，负责对召回候选做精排
    reranker: Reranker
    # 元数据仓储，负责在召回结果合并时补齐字段 表 主外键等结构信息
    meta_mysql_repository: MetaMySQLRepository
    # 数仓仓储，负责在额外上下文补全时读取数据库方言 版本等执行环境信息
    dw_mysql_repository: DWMySQLRepository
