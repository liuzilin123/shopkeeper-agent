"""
字段召回节点

负责根据关键词从字段知识库中召回候选字段
它解决的是“用户问题可能对应哪些数据库字段”的问题
当前主线是：关键词扩展 -> 稠密向量(Qdrant) + 稀疏全文(ES) -> RRF 融合 -> Reranker 精排
"""

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.reranker import render_column_candidate
from app.agent.retrieval.rrf import reciprocal_rank_fusion
from app.agent.state import DataAgentState
from app.core.log import logger
from app.entities.column_info import ColumnInfo
from app.prompt.prompt_loader import load_prompt


async def recall_column(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """召回和用户问题语义相关的字段元数据"""

    writer = runtime.stream_writer
    step = "召回字段信息"
    writer({"type": "progress", "step": step, "status": "running"})

    try:
        # state 保存图内业务中间结果：原始问题和上游抽取出的关键词
        keywords = state["keywords"]
        query = state["query"]
        # context 保存外部运行时工具：稠密/稀疏两个召回通道和 Embedding、Reranker
        column_qdrant_repository = runtime.context["column_qdrant_repository"]
        column_es_repository = runtime.context["column_es_repository"]
        embedding_client = runtime.context["embedding_client"]
        reranker = runtime.context["reranker"]

        # 用 LLM 把用户问法扩展成“字段语义”列表，例如“销售总额”可扩展出“销售金额”
        prompt = PromptTemplate(
            template=load_prompt("extend_keywords_for_column_recall"),
            input_variables=["query"],
        )
        # 提示词要求模型只输出 JSON 数组，解析后 result 就是 list[str]
        output_parser = JsonOutputParser()
        # LCEL 管道：填充提示词 -> 调用模型 -> 解析 JSON
        chain = prompt | llm | output_parser

        result = await chain.ainvoke({"query": query})

        # 原始关键词和 LLM 扩展词一起参与召回；set 去重，避免重复请求同一关键词
        keywords = set(keywords + result)

        # 稠密向量 + 稀疏全文两条通道分别召回，再用 RRF 融合成统一候选分
        candidate_map: dict[str, ColumnInfo] = {}
        candidate_scores: dict[str, float] = {}
        for keyword in keywords:
            # 查询词必须先转成向量，才能和写入 Qdrant 的字段向量做相似度检索
            embedding = await embedding_client.aembed_query(keyword)
            dense_results = await column_qdrant_repository.search(embedding)
            sparse_results = await column_es_repository.search(keyword)

            # 两路结果都按相关度有序，RRF 只需要各自的排序位置即可融合
            for column_info in dense_results + sparse_results:
                candidate_map.setdefault(column_info.id, column_info)
            fused = reciprocal_rank_fusion([dense_results, sparse_results])
            for column_id, score in fused.items():
                if score > candidate_scores.get(column_id, 0.0):
                    candidate_scores[column_id] = score

        # 候选统一交给 Reranker 做精排，让最相关的字段排到最前面
        candidates: list[ColumnInfo] = list(candidate_map.values())
        if candidates:
            items = [
                (column_info.id, render_column_candidate(column_info))
                for column_info in candidates
            ]
            ranked_ids = await reranker.rerank(query, items)
            id_to_column = {column_info.id: column_info for column_info in candidates}
            retrieved_column_infos = [
                id_to_column[column_id]
                for column_id in ranked_ids
                if column_id in id_to_column
            ]
        else:
            retrieved_column_infos = []

        writer({"type": "progress", "step": step, "status": "success"})
        return {"retrieved_column_infos": retrieved_column_infos}
    except Exception as e:
        logger.error(f"{step} failed: {e}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise
