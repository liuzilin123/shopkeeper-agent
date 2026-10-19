"""
RRF 融合工具

把多个召回通道各自返回的有序候选列表，用 Reciprocal Rank Fusion 规则融合成一个分数
稠密向量召回和稀疏全文召回各给一份按相关度排序的列表，融合后按 id 累加得分
"""

from typing import TypeVar

T = TypeVar("T")


def reciprocal_rank_fusion(
    ranked_lists: list[list[T]], k: int = 60
) -> dict[str, float]:
    """按实体 id 累加 1/(k + rank + 1)，返回 id 到融合分的映射"""
    scores: dict[str, float] = {}
    for ranked_list in ranked_lists:
        # rank 从 0 开始，越靠前的候选权重越大
        for rank, item in enumerate(ranked_list):
            item_id = getattr(item, "id")
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank + 1)
    return scores
