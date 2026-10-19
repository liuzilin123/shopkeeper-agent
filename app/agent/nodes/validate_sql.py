"""
SQL 校验节点

负责在真正执行查询前，用数据库解析一次生成的 SQ
校验结果不在这里决定流程走向，而是通过 state["error"] 交给 graph.py 的条件边判断
"""

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.sql_guard import SqlGuardError, validate_sql_security
from app.agent.state import DataAgentState
from app.core.log import logger
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository


async def validate_sql(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """校验 SQL，并返回 error 字段控制后续条件分支"""

    writer = runtime.stream_writer
    step = "校验SQL"
    writer({"type": "progress", "step": step, "status": "running"})

    try:
        # 读取 generate_sql 或 correct_sql 写入状态的候选 SQL
        sql = state["sql"]

        # SQL 可用性必须交给真实数仓判断，这里从运行时上下文取 DW Repository
        dw_mysql_repository: DWMySQLRepository = runtime.context["dw_mysql_repository"]

        # 第一步：AST 静态校验，本地拦截写操作、多语句、危险函数和越权访问
        # 白名单取本次查询被授予看到的表，越界访问（如 information_schema）直接拒绝
        allowed_tables = {table_info["name"] for table_info in state["table_infos"]}
        try:
            validate_sql_security(sql, allowed_tables)
        except SqlGuardError as e:
            logger.info(f"SQL安全校验失败：{e}")
            writer({"type": "progress", "step": step, "status": "success"})
            return {"error": f"SQL 安全校验失败：{e}"}

        # 第二步：用数据库 EXPLAIN 做真实解析校验，发现表名 字段名等语法错误
        try:
            await dw_mysql_repository.validate(sql)
            writer({"type": "progress", "step": step, "status": "success"})
            logger.info("SQL语法正确")
            return {"error": None}
        except Exception as e:
            # 不抛出异常中断图执行，而是把错误写入状态，供条件分支进入 correct_sql
            logger.info(f"SQL语法错误：{str(e)}")
            writer({"type": "progress", "step": step, "status": "success"})
            return {"error": str(e)}

    except Exception as e:
        logger.error(f"{step} failed: {e}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise
