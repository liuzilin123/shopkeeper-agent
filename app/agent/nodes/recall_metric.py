"""
指标召回节点

负责根据用户问题从指标知识库中召回候选指标
它帮助 Agent 把“销售额 转化率 客单价”等业务表达映射到已定义指标
实现路径和字段召回类似：关键词扩展 -> 稠密向量(Qdrant) + 稀疏全文(ES) -> RRF 融合 -> Reranker 精排
"""

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.reranker import render_metric_candidate
from app.agent.retrieval.rrf import reciprocal_rank_fusion
from app.agent.state import DataAgentState
from app.conf.app_config import app_config
from app.core.log import logger
from app.entities.metric_info import MetricInfo
from app.prompt.prompt_loader import load_prompt


async def recall_metric(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """召回和用户问题语义相关的业务指标"""

    writer = runtime.stream_writer
    step = "召回指标信息"
    writer({"type": "progress", "step": step, "status": "running"})

    try:
        # query 用于让 LLM 生成指标层检索词，keywords 来自上游的通用关键词抽取
        query = state["query"]
        keywords = state["keywords"]
        # 指标召回使用稠密向量 + 稀疏全文两路，需要 Embedding、Qdrant、ES 和 Reranker
        embedding_client = runtime.context["embedding_client"]
        metric_qdrant_repository = runtime.context["metric_qdrant_repository"]
        metric_es_repository = runtime.context["metric_es_repository"]
        reranker = runtime.context["reranker"]

        # 用 LLM 把用户问法扩展成“指标概念”列表，例如“销售总额”可扩展出“GMV”“成交额”
        prompt = PromptTemplate(
            template=load_prompt("extend_keywords_for_metric_recall"),
            input_variables=["query"],
        )
        # 指标扩展 prompt 要求只输出 JSON 数组，解析后 result 就是 list[str]
        output_parser = JsonOutputParser()
        # LCEL 管道：填充提示词 -> 调用模型 -> 解析 JSON
        chain = prompt | llm | output_parser

        result = await chain.ainvoke({"query": query})

        # 通用关键词和指标扩展词都参与召回，提升同义指标的命中率
        keywords = set(keywords + result)

        # 稠密向量 + 稀疏全文两条通道分别召回，再用 RRF 融合成统一候选分
        candidate_map: dict[str, MetricInfo] = {}
        candidate_scores: dict[str, float] = {}
        for keyword in keywords:
            embedding = await embedding_client.aembed_query(keyword)
            dense_results = await metric_qdrant_repository.search(embedding)
            sparse_results = await metric_es_repository.search(keyword)

            for metric_info in dense_results + sparse_results:
                candidate_map.setdefault(metric_info.id, metric_info)
            fused = reciprocal_rank_fusion([dense_results, sparse_results])
            for metric_id, score in fused.items():
                if score > candidate_scores.get(metric_id, 0.0):
                    candidate_scores[metric_id] = score

        # 按 RRF 融合分从高到低排序；分数相同时用 id 兜底，避免依赖 set 遍历顺序
        ranked_candidates: list[MetricInfo] = sorted(
            candidate_map.values(),
            key=lambda metric_info: (
                -candidate_scores.get(metric_info.id, 0.0),
                metric_info.id,
            ),
        )
        # 只把 RRF 排名靠前的候选交给 Reranker，既让融合分参与最终排序，也控制重排成本
        candidates = ranked_candidates[: app_config.retrieval.recall_top_k]

        # 候选统一交给 Reranker 做精排，让最相关的指标排到最前面
        if candidates:
            items = [
                (metric_info.id, render_metric_candidate(metric_info))
                for metric_info in candidates
            ]
            ranked_ids = await reranker.rerank(query, items)
            id_to_metric = {metric_info.id: metric_info for metric_info in candidates}
            retrieved_metric_infos = [
                id_to_metric[metric_id]
                for metric_id in ranked_ids
                if metric_id in id_to_metric
            ]
        else:
            retrieved_metric_infos = []

        logger.info(
            f"指标召回候选 {len(ranked_candidates)} 个，"
            f"RRF 截断后 {len(candidates)} 个进入重排"
        )
        logger.info(f"检索到指标信息：{[m.id for m in retrieved_metric_infos]}")
        writer({"type": "progress", "step": step, "status": "success"})
        return {"retrieved_metric_infos": retrieved_metric_infos}
    except Exception as e:
        logger.error(f"{step} failed: {e}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise
