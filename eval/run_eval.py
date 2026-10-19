"""
固定问数测试集评测脚本

逐条跑固定测试集：把每条问题的黄金 SQL 在真实数仓上执行得到期望结果，
再跑完整问数链路得到 Agent 生成的 SQL 和结果，两者对比计算 SQL 执行正确率。

用法：
    uv run python -m eval.run_eval                        # 默认混合召回 + LLM Reranker
    uv run python -m eval.run_eval --no-rerank            # 关闭 Reranker 做 ablation
    uv run python -m eval.run_eval --dense-only           # 只走稠密向量召回，关闭稀疏通道
"""

import argparse
import asyncio
import sys
from decimal import Decimal
from pathlib import Path

import yaml

from app.agent.context import DataAgentContext
from app.agent.graph import graph
from app.agent.llm import llm
from app.agent.reranker import LLMReranker, NoopReranker
from app.agent.state import DataAgentState
from app.clients.embedding_client_manager import embedding_client_manager
from app.clients.es_client_manager import es_client_manager
from app.clients.mysql_client_manager import (
    dw_mysql_client_manager,
    dw_mysql_readonly_client_manager,
    meta_mysql_client_manager,
)
from app.clients.qdrant_client_manager import qdrant_client_manager
from app.repositories.es.column_es_repository import ColumnESRepository
from app.repositories.es.metric_es_repository import MetricESRepository
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository


class _EmptyColumnESRepository:
    """稠密召回 ablation 用的空稀疏通道，search 恒返回空列表"""

    async def search(self, keyword, score_threshold=0.5, limit=20):
        return []


class _EmptyMetricESRepository:
    """稠密召回 ablation 用的空稀疏通道，search 恒返回空列表"""

    async def search(self, keyword, score_threshold=0.5, limit=20):
        return []


def _to_number(value):
    """把 asyncmy 返回的 Decimal 归一化成 float，便于跨结果比较"""
    if isinstance(value, Decimal):
        return float(value)
    return value


def _canonical(rows: list[dict]) -> list[tuple]:
    """把结果行集合归一化成可比较的规范形式，忽略列名和行列顺序差异"""
    row_tuples = []
    for row in rows:
        values = []
        for value in row.values():
            value = _to_number(value)
            if isinstance(value, float):
                value = round(value, 6)
            values.append(value)

        def _key(item):
            return (type(item).__name__, str(item))

        row_tuples.append(tuple(sorted(values, key=_key)))

    def _row_key(t):
        return [(type(item).__name__, str(item)) for item in t]

    return sorted(row_tuples, key=_row_key)


def _results_equal(actual: list[dict], expected: list[dict]) -> bool:
    """对比两组结果，浮点保留 6 位精度后按多集合比较"""
    return _canonical(actual) == _canonical(expected)


async def run_eval(test_set_path: str, dense_only: bool, no_rerank: bool):
    """执行评测并返回 (执行成功率, 结果正确率, 明细列表)"""

    qdrant_client_manager.init()
    embedding_client_manager.init()
    es_client_manager.init()
    meta_mysql_client_manager.init()
    dw_mysql_client_manager.init()
    dw_mysql_readonly_client_manager.init()

    test_set = yaml.safe_load(Path(test_set_path).read_text(encoding="utf-8"))

    async with (
        meta_mysql_client_manager.session_factory() as meta_session,
        dw_mysql_client_manager.session_factory() as dw_session,
        dw_mysql_readonly_client_manager.session_factory() as dw_readonly_session,
    ):
        meta_mysql_repository = MetaMySQLRepository(meta_session)
        dw_mysql_repository = DWMySQLRepository(dw_session, dw_readonly_session)
        column_qdrant_repository = ColumnQdrantRepository(qdrant_client_manager.client)
        metric_qdrant_repository = MetricQdrantRepository(qdrant_client_manager.client)
        value_es_repository = ValueESRepository(es_client_manager.client)

        # 稀疏通道可被关闭，用来量化混合召回相比纯向量召回的提升
        if dense_only:
            column_es_repository = _EmptyColumnESRepository()
            metric_es_repository = _EmptyMetricESRepository()
        else:
            column_es_repository = ColumnESRepository(es_client_manager.client)
            metric_es_repository = MetricESRepository(es_client_manager.client)

        reranker = NoopReranker() if no_rerank else LLMReranker(llm)

        context = DataAgentContext(
            column_qdrant_repository=column_qdrant_repository,
            column_es_repository=column_es_repository,
            embedding_client=embedding_client_manager.client,
            metric_qdrant_repository=metric_qdrant_repository,
            metric_es_repository=metric_es_repository,
            value_es_repository=value_es_repository,
            reranker=reranker,
            meta_mysql_repository=meta_mysql_repository,
            dw_mysql_repository=dw_mysql_repository,
        )

        total = len(test_set)
        executed = 0
        correct = 0
        details = []

        for case in test_set:
            query = case["query"]
            golden_sql = case["expected_sql"]

            try:
                golden_result = await dw_mysql_repository.run(golden_sql)
            except Exception as e:
                details.append(
                    {"query": query, "status": "golden_error", "detail": str(e)}
                )
                continue

            try:
                final_state = await graph.ainvoke(
                    DataAgentState(query=query), context=context
                )
                executed += 1
                actual = final_state.get("result", [])
                if _results_equal(actual, golden_result):
                    correct += 1
                    details.append(
                        {"query": query, "status": "pass", "sql": final_state.get("sql")}
                    )
                else:
                    details.append(
                        {
                            "query": query,
                            "status": "mismatch",
                            "sql": final_state.get("sql"),
                            "actual": actual,
                            "expected": golden_result,
                        }
                    )
            except Exception as e:
                details.append({"query": query, "status": "exec_error", "detail": str(e)})

    await qdrant_client_manager.close()
    await es_client_manager.close()
    await meta_mysql_client_manager.close()
    await dw_mysql_client_manager.close()
    await dw_mysql_readonly_client_manager.close()

    exec_rate = executed / total if total else 0.0
    correct_rate = correct / total if total else 0.0
    return exec_rate, correct_rate, details


def _print_report(exec_rate, correct_rate, details):
    print("\n" + "=" * 80)
    print("固定问数测试集评测结果")
    print("=" * 80)
    for i, detail in enumerate(details, start=1):
        status = detail["status"]
        mark = {
            "pass": "[PASS]",
            "mismatch": "[FAIL]",
            "exec_error": "[FAIL]",
            "golden_error": "[WARN]",
        }[status]
        print(f"\n[{i}] {mark} {detail['query']}")
        if status == "mismatch":
            print(f"    生成 SQL：{detail.get('sql')}")
            print(f"    实际结果：{detail.get('actual')}")
            print(f"    期望结果：{detail.get('expected')}")
        elif status in ("exec_error", "golden_error"):
            print(f"    错误：{detail.get('detail')}")
        else:
            print(f"    生成 SQL：{detail.get('sql')}")
    print("\n" + "=" * 80)
    print(f"执行成功率：{exec_rate * 100:.1f}%")
    print(f"结果正确率（SQL 执行正确率）：{correct_rate * 100:.1f}%")
    print("=" * 80)


if __name__ == "__main__":
    # Windows 默认控制台是 GBK，强制用 UTF-8 输出避免中文和符号报错
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(description="固定问数测试集评测")
    parser.add_argument(
        "--test-set", default=str(Path(__file__).parent / "test_set.yaml")
    )
    parser.add_argument("--dense-only", action="store_true", help="只走稠密向量召回")
    parser.add_argument("--no-rerank", action="store_true", help="关闭 Reranker 重排")
    args = parser.parse_args()

    exec_rate, correct_rate, details = asyncio.run(
        run_eval(args.test_set, args.dense_only, args.no_rerank)
    )
    _print_report(exec_rate, correct_rate, details)
