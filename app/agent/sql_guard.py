"""
SQL 安全守卫

在 SQL 真正进入数据库之前，先用 sqlglot 把它解析成 AST 做一轮静态校验，
只放行“只读、单条、未越权、无危险函数”的查询。这里解决的是 EXPLAIN 校验
覆盖不到的几类风险：多语句注入、写操作、INTO OUTFILE 写文件、SLEEP/BENCHMARK
等资源消耗或信息泄露函数，以及访问未授权表。

它和只读账户互为纵深防御：AST 校验给出可回传给模型的明确错误信息，
只读账户兜底保证即使校验被绕过，数据库层也拒绝写操作。
"""

import re

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

# 危险函数黑名单：延时、锁、读取文件、复制状态等可能被滥用的 MySQL 函数
DANGEROUS_FUNCTIONS = {
    "SLEEP",
    "BENCHMARK",
    "LOAD_FILE",
    "GET_LOCK",
    "RELEASE_LOCK",
    "IS_FREE_LOCK",
    "IS_USED_LOCK",
    "GTID_SUBSET",
    "GTID_SUBTRACT",
    "MASTER_POS_WAIT",
    "UPDATEXML",
    "EXTRACTVALUE",
}

# INTO OUTFILE / DUMPFILE 会让 mysql 方言的 sqlglot 解析失败，先做一次文本级拦截
_INTO_FILE_PATTERN = re.compile(r"\bINTO\s+(OUTFILE|DUMPFILE)\b", re.IGNORECASE)


class SqlGuardError(Exception):
    """SQL 未通过安全校验，message 会作为修正提示回传给 correct_sql"""


def validate_sql_security(sql: str, allowed_tables: set[str]) -> None:
    """校验 SQL 是否满足只读、单条、未越权、无危险函数。失败时抛 SqlGuardError"""

    if _INTO_FILE_PATTERN.search(sql):
        raise SqlGuardError("禁止使用 INTO OUTFILE / INTO DUMPFILE 把查询结果写入文件")

    try:
        statements = sqlglot.parse(sql, read="mysql")
    except ParseError as e:
        raise SqlGuardError(f"SQL 无法解析：{e}") from e

    if len(statements) != 1:
        raise SqlGuardError("只允许输出单条 SQL 语句，禁止用分号拼接多条语句")

    statement = statements[0]

    # 顶层只允许 SELECT 和 UNION，其余类型（INSERT/UPDATE/DELETE/DDL/SHOW 等）一律拒绝
    if not isinstance(statement, (exp.Select, exp.Union)):
        raise SqlGuardError("只允许只读查询，禁止 INSERT/UPDATE/DELETE/DDL 等写操作")

    for func in statement.find_all(exp.Func):
        # 危险函数在 sqlglot 中大多解析为 Anonymous，只能用 name 取真实函数名
        name = func.name.upper() if isinstance(func, exp.Anonymous) else func.sql_name().upper()
        if name in DANGEROUS_FUNCTIONS:
            raise SqlGuardError(f"禁止使用危险函数 {name}")

    # CTE 名在 AST 里也会以 Table 节点出现，先收集起来避免误判为真实表
    cte_names = {cte.alias_or_name for cte in statement.ctes}
    allowed_lower = {table.lower() for table in allowed_tables}
    for table in statement.find_all(exp.Table):
        name = table.name
        # 派生表/子查询不会暴露成 Table 节点；无名字或 CTE 引用直接跳过
        if not name or name in cte_names:
            continue
        if table.db:
            raise SqlGuardError(
                f"禁止访问带 schema 前缀的表 {table.db}.{name}，只能使用无前缀的业务表"
            )
        if name.lower() not in allowed_lower:
            raise SqlGuardError(f"禁止访问未授权表 {name}")
