"""
结果解释节点

负责在 SQL 执行完成后，用大模型对查询结果做自然语言解释，并推荐合适的图表。
它是体验增强节点，位于 run_sql 之后：即使解释失败也返回兜底文案，不中断问数主链路。
"""

import json

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt

# 结果解释最多携带的字符数，避免把超大结果塞进提示词撑爆上下文
MAX_RESULT_CHARS = 4000


def _serialize_result(result: list[dict]) -> str:
    """把查询结果序列化并截断，控制提示词长度"""
    text = json.dumps(result, ensure_ascii=False, default=str)
    if len(text) <= MAX_RESULT_CHARS:
        return text
    return text[:MAX_RESULT_CHARS] + "...(已截断)"


async def explain_result(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """解释查询结果并推荐图表"""

    writer = runtime.stream_writer
    step = "解释结果"
    writer({"type": "progress", "step": step, "status": "running"})

    query = state["query"]
    sql = state.get("sql", "")
    result = state.get("result", []) or []

    # 结果为空时给一个通用解释，不调用大模型
    if not result:
        explanation = "查询完成，但没有匹配到符合条件的数据。"
        writer({"type": "explanation", "data": explanation})
        writer({"type": "chart", "data": None})
        writer({"type": "progress", "step": step, "status": "success"})
        return {"explanation": explanation, "chart_spec": {}}

    try:
        prompt = PromptTemplate(
            template=load_prompt("explain_result"),
            input_variables=["query", "sql", "result"],
        )
        output_parser = JsonOutputParser()
        chain = prompt | llm | output_parser

        parsed = await chain.ainvoke(
            {
                "query": query,
                "sql": sql,
                "result": _serialize_result(result),
            }
        )

        explanation = parsed.get("explanation", "") if isinstance(parsed, dict) else ""
        chart_spec = parsed.get("chart") if isinstance(parsed, dict) else None
        if not isinstance(chart_spec, dict):
            chart_spec = {}

        logger.info(f"结果解释：{explanation}")
        logger.info(f"图表推荐：{chart_spec}")

        writer({"type": "explanation", "data": explanation})
        writer({"type": "chart", "data": chart_spec or None})
        writer({"type": "progress", "step": step, "status": "success"})
        return {"explanation": explanation, "chart_spec": chart_spec}
    except Exception as e:
        # 解释失败属于体验降级，给出兜底文案后正常结束，不抛出异常
        logger.error(f"{step} failed: {e}")
        fallback = f"查询完成，共 {len(result)} 行结果。"
        writer({"type": "explanation", "data": fallback})
        writer({"type": "chart", "data": None})
        writer({"type": "progress", "step": step, "status": "success"})
        return {"explanation": fallback, "chart_spec": {}}
