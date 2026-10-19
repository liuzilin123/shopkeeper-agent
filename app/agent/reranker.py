"""
Reranker 重排器

负责在召回候选之上做精排，把与用户问题最相关的候选排到最前面
当前提供 LLM 列表式重排实现，接口保持可插拔，后续可无缝换成交叉编码器模型
"""

from abc import ABC, abstractmethod

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate

from app.entities.column_info import ColumnInfo
from app.entities.metric_info import MetricInfo
from app.prompt.prompt_loader import load_prompt


def render_column_candidate(column_info: ColumnInfo) -> str:
    """把字段候选渲染成重排器可读的文本，聚合字段名 别名 描述 角色和所属表"""
    alias = " ".join(column_info.alias) if column_info.alias else ""
    return (
        f"{column_info.name}（{alias}）：{column_info.description} "
        f"角色={column_info.role}，所属表={column_info.table_id}"
    )


def render_metric_candidate(metric_info: MetricInfo) -> str:
    """把指标候选渲染成重排器可读的文本，聚合指标名 别名 描述和公式"""
    alias = " ".join(metric_info.alias) if metric_info.alias else ""
    return (
        f"{metric_info.name}（{alias}）：{metric_info.description} "
        f"公式={metric_info.formula}"
    )


class Reranker(ABC):
    """重排器抽象接口，items 为 (id, 描述文本) 列表"""

    @abstractmethod
    async def rerank(self, query: str, items: list[tuple[str, str]]) -> list[str]:
        """按与 query 的相关性从高到低返回 id 列表"""


class NoopReranker(Reranker):
    """不做重排，原样返回候选 id，供评测做 ablation 对比"""

    async def rerank(self, query: str, items: list[tuple[str, str]]) -> list[str]:
        return [item_id for item_id, _ in items]


class LLMReranker(Reranker):
    """用大模型做列表式（listwise）重排"""

    def __init__(self, llm):
        self.llm = llm

    async def rerank(self, query: str, items: list[tuple[str, str]]) -> list[str]:
        if not items:
            return []

        prompt = PromptTemplate(
            template=load_prompt("rerank"), input_variables=["query", "candidates"]
        )
        chain = prompt | self.llm | JsonOutputParser()

        # 用 id：文本 逐行列出候选，让模型在候选集合内排序而不是自由发挥
        candidates_text = "\n".join(f"{item_id}：{text}" for item_id, text in items)

        try:
            ranked_ids: list = await chain.ainvoke(
                {"query": query, "candidates": candidates_text}
            )
        except Exception:
            # 解析失败时退化为原顺序，保证重排器不会因为模型输出异常中断整条链路
            return [item_id for item_id, _ in items]

        # 只保留模型给出且真实存在于候选里的 id；漏掉的候选追加到末尾兜底
        valid_ids: list[str] = []
        seen: set[str] = set()
        for item_id in ranked_ids:
            if item_id in seen:
                continue
            seen.add(item_id)
            valid_ids.append(item_id)
        for item_id, _ in items:
            if item_id not in seen:
                valid_ids.append(item_id)
        return valid_ids
