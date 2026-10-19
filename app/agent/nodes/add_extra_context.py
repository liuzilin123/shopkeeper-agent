"""
额外上下文补全节点

负责在 SQL 生成前补齐不来自召回结果、但模型必须知道的运行环境信息
当前包括日期信息和数据库方言/版本，后续可继续扩展权限、租户、时区等上下文
"""

from datetime import date

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState, DateInfoState, DBInfoState, JoinInfoState
from app.core.log import logger


def _build_join_infos(table_infos: list) -> list[JoinInfoState]:
    """从已选表的外键 reference 派生 JOIN 边，只保留两端表都在候选内的边"""
    table_names = {table_info["name"] for table_info in table_infos}
    join_infos: list[JoinInfoState] = []
    for table_info in table_infos:
        for column in table_info["columns"]:
            # 只有外键且配置了引用目标才参与 JOIN 图谱
            if column.get("role") != "foreign_key" or not column.get("reference"):
                continue
            # reference 形如 dim_region.region_id，拆成目标表和目标字段
            right_table, right_column = column["reference"].split(".", 1)
            if right_table in table_names:
                join_infos.append(
                    JoinInfoState(
                        left_table=table_info["name"],
                        left_column=column["name"],
                        right_table=right_table,
                        right_column=right_column,
                    )
                )
    return join_infos


async def add_extra_context(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """补齐 SQL 生成所需的日期、数据库环境和多表 JOIN 关系信息"""

    writer = runtime.stream_writer
    step = "添加额外上下文"
    writer({"type": "progress", "step": step, "status": "running"})
    try:
        dw_mysql_repository = runtime.context["dw_mysql_repository"]

        # 当前日期信息会帮助模型处理“今天 本月 本季度 最近 N 天”等相对时间表达
        today = date.today()
        date_str = today.strftime("%Y-%m-%d")
        weekday = today.strftime("%A")
        quarter = f"Q{(today.month - 1) // 3 + 1}"
        date_info = DateInfoState(date=date_str, weekday=weekday, quarter=quarter)

        # 数据库方言和版本会影响函数名 日期运算 limit 语法等 SQL 细节
        db = await dw_mysql_repository.get_db_info()
        db_info = DBInfoState(**db)

        # JOIN 图谱：由过滤后的表外键引用派生，帮模型写出正确的多表关联条件
        join_infos = _build_join_infos(state["table_infos"])

        logger.info(f"数据库信息：{db_info}")
        logger.info(f"日期信息：{date_info}")
        logger.info(f"JOIN 关系：{join_infos}")

        writer({"type": "progress", "step": step, "status": "success"})
        return {"date_info": date_info, "db_info": db_info, "join_infos": join_infos}

    except Exception as e:
        logger.error(f"{step} failed: {e}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise
