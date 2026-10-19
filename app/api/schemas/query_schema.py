"""
问数接口请求体定义

集中声明 API 层输入输出的数据结构，让路由函数只处理业务流程，
字段校验和 OpenAPI 文档生成交给 Pydantic 与 FastAPI 完成。
"""

from pydantic import BaseModel


class HistoryTurn(BaseModel):
    """一轮历史对话，role 取值 user/assistant，content 为该轮文本内容"""

    role: str
    content: str


class QuerySchema(BaseModel):
    """`/api/query` 请求体，承载用户输入的自然语言问题和可选的历史对话"""

    # 前端请求体中的 query 字段，例如 {"query": "统计华北地区销售额"}
    query: str
    # 多轮追问的历史对话，按时间顺序排列；单轮问数时不传或传空列表
    history: list[HistoryTurn] = []
