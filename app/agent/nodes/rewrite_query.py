"""
追问改写节点

负责在多轮问数场景下，把用户带指代、省略或延续的追问改写成自包含的完整问题。
单轮问数（无历史）时直接透传，不额外调用大模型。
改写后的 query 会覆盖状态，下游所有节点统一使用改写后的完整问题。
"""

import yaml
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


async def rewrite_query(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """结合历史对话把追问改写为自包含问题，无历史时透传"""

    writer = runtime.stream_writer
    step = "理解追问"
    writer({"type": "progress", "step": step, "status": "running"})

    try:
        query = state["query"]
        history = state.get("history", []) or []

        # 单轮问数没有历史，无需改写，直接透传原始问题
        if not history:
            writer({"type": "progress", "step": step, "status": "success"})
            return {}

        prompt = PromptTemplate(
            template=load_prompt("rewrite_query"),
            input_variables=["history", "query"],
        )
        output_parser = StrOutputParser()
        chain = prompt | llm | output_parser

        result = await chain.ainvoke(
            {
                "history": yaml.dump(history, allow_unicode=True, sort_keys=False),
                "query": query,
            }
        )
        rewritten = result.strip()
        if not rewritten:
            writer({"type": "progress", "step": step, "status": "success"})
            return {}

        logger.info(f"追问改写：{query} -> {rewritten}")
        writer({"type": "progress", "step": step, "status": "success"})
        # 覆盖 query，下游关键词抽取、过滤、SQL 生成都基于改写后的完整问题
        return {"query": rewritten}
    except Exception as e:
        # 改写是增强能力，失败时保留原问题继续执行，不中断问数主链路
        logger.error(f"{step} failed: {e}")
        writer({"type": "progress", "step": step, "status": "success"})
        return {}
