"""
电商问数 Agent 状态定义

State 是 LangGraph 各节点之间传递和更新的共享数据
本章在用户原始问题之外，新增关键词列表和三路召回结果
并把召回到的实体整理成后续提示词更容易消费的表信息和指标信息
SQL 生成闭环会继续写入候选 SQL 以及校验错误信息，用于控制校正或执行分支
"""

from typing import TypedDict

from app.entities.column_info import ColumnInfo
from app.entities.metric_info import MetricInfo
from app.entities.value_info import ValueInfo


class MetricInfoState(TypedDict):
    """面向 SQL 生成提示词的指标信息"""

    name: str
    description: str
    # 指标依赖的字段 id，用来提示模型不要脱离业务口径随意计算
    relevant_columns: list[str]
    alias: list[str]
    # 指标可执行计算公式，存在时模型必须严格按该表达式聚合
    formula: str


class ColumnInfoState(TypedDict):
    """表上下文中的字段信息"""

    name: str
    type: str
    role: str
    # 字段真实样例值，尤其用于辅助 where 条件里的枚举值选择
    examples: list
    description: str
    alias: list[str]
    # 外键引用的目标字段，用于派生多表 JOIN 关系
    reference: str | None


class TableInfoState(TypedDict):
    """SQL 生成阶段真正传给模型的表结构上下文"""

    name: str
    role: str
    description: str
    columns: list[ColumnInfoState]


class JoinInfoState(TypedDict):
    """一条表关联边，用于告诉模型多表查询时使用哪组主外键关联"""

    left_table: str
    left_column: str
    right_table: str
    right_column: str


class DateInfoState(TypedDict):
    """SQL 生成阶段使用的当前日期上下文"""

    date: str
    weekday: str
    quarter: str


class DBInfoState(TypedDict):
    """SQL 生成阶段使用的数据库环境信息"""

    dialect: str
    version: str


class DataAgentState(TypedDict):
    """一次问数链路中的核心状态"""

    query: str  # 用户输入的查询（多轮追问时会被改写为自包含问题）
    history: list[dict]  # 多轮对话历史，用于追问改写，单轮问数为空
    keywords: list[str]  # 抽取的关键词
    retrieved_column_infos: list[ColumnInfo]  # 检索到的字段信息
    retrieved_metric_infos: list[MetricInfo]  # 检索到的指标信息
    retrieved_value_infos: list[ValueInfo]  # 检索到的取值信息

    table_infos: list[TableInfoState]  # 合并和补齐后的表结构上下文
    metric_infos: list[MetricInfoState]  # 合并后的指标上下文
    date_info: DateInfoState  # 当前日期 星期和季度信息
    db_info: DBInfoState  # 数据库方言和版本信息
    join_infos: list[JoinInfoState]  # 最终选中表之间的 JOIN 关联边

    sql: str  # 生成或校正后的SQL
    result: list[dict]  # SQL 执行结果行，供下游消费或评测读取
    explanation: str  # 对查询结果的自然语言解释
    chart_spec: dict  # 图表推荐，形如 {"type","x_axis","y_axis","title"}

    error: str  # 校验SQL时出现的错误信息

    correct_count: int  # SQL 已修正次数，用于限制校验-修正回环，避免无限循环
