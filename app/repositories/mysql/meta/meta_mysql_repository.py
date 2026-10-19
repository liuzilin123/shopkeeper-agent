"""
元数据库 MySQL 仓储

这一层对应文档里的 Meta Repository，负责接收业务实体并落到 Meta MySQL
Repository 自身只关心“如何写入”，而“哪些写操作要放在同一笔事务里”，由 Service 层统一决定

表 字段 指标和字段指标关系都会先以业务实体流转，再在这里统一转成 ORM 模型
问数链路运行时也会从这里读取元数据，用来把召回到的 id 补齐成完整实体
"""

from sqlalchemy import text
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.column_info import ColumnInfo
from app.entities.column_metric import ColumnMetric
from app.entities.metric_info import MetricInfo
from app.entities.table_info import TableInfo
from app.models.column_info import ColumnInfoMySQL
from app.models.table_info import TableInfoMySQL
from app.repositories.mysql.meta.mappers.column_info_mapper import ColumnInfoMapper
from app.repositories.mysql.meta.mappers.column_metric_mapper import ColumnMetricMapper
from app.repositories.mysql.meta.mappers.metric_info_mapper import MetricInfoMapper
from app.repositories.mysql.meta.mappers.table_info_mapper import TableInfoMapper


class MetaMySQLRepository:
    """负责把元数据业务实体持久化到 Meta MySQL"""

    def __init__(self, session: AsyncSession):
        self.session = session

    def _to_values(self, model) -> dict:
        """把 ORM 模型转成列名到值的字典，供 MySQL upsert 批量插入使用"""
        return {
            col.name: getattr(model, col.name)
            for col in type(model).__table__.columns
        }

    async def _upsert(self, models: list) -> None:
        """按主键幂等写入：已存在则用新值覆盖，不存在则插入，避免重复构建冲突"""
        if not models:
            return

        model_cls = type(models[0])
        stmt = mysql_insert(model_cls).values(
            [self._to_values(model) for model in models]
        )

        # 主键之外的列在发生冲突时用本次的新值覆盖，主键保持不变
        primary_key_names = {
            col.name for col in model_cls.__table__.primary_key.columns
        }
        update_assignments = {
            col.name: stmt.inserted[col.name]
            for col in model_cls.__table__.columns
            if col.name not in primary_key_names
        }

        if update_assignments:
            stmt = stmt.on_duplicate_key_update(**update_assignments)
        else:
            # column_metric 只有联合主键，冲突时用主键自赋值充当无操作更新
            noop_column = next(iter(primary_key_names))
            stmt = stmt.on_duplicate_key_update(
                **{noop_column: stmt.inserted[noop_column]}
            )

        await self.session.execute(stmt)

    async def save_table_infos(self, table_infos: list[TableInfo]):
        """按主键幂等保存表元数据。重复构建时覆盖旧值而不是触发主键冲突"""
        await self._upsert(
            [TableInfoMapper.to_model(table_info) for table_info in table_infos]
        )

    async def save_column_infos(self, column_infos: list[ColumnInfo]):
        """按主键幂等保存字段元数据。实体到模型的转换统一通过 Mapper 完成"""
        await self._upsert(
            [ColumnInfoMapper.to_model(column_info) for column_info in column_infos]
        )

    async def save_metric_infos(self, metric_infos: list[MetricInfo]):
        """按主键幂等保存指标元数据。指标本身和字段关联关系分开写入"""
        await self._upsert(
            [MetricInfoMapper.to_model(metric_info) for metric_info in metric_infos]
        )

    async def save_column_metrics(self, column_metrics: list[ColumnMetric]):
        """按联合主键幂等保存字段与指标的关联关系"""
        await self._upsert(
            [
                ColumnMetricMapper.to_model(column_metric)
                for column_metric in column_metrics
            ]
        )

    async def get_column_info_by_id(self, id: str) -> ColumnInfo | None:
        """按字段 id 查询字段元数据，供召回信息合并阶段补齐字段上下文"""

        column_info: ColumnInfoMySQL | None = await self.session.get(
            ColumnInfoMySQL, id
        )
        if column_info:
            return ColumnInfoMapper.to_entity(column_info)
        else:
            return None

    async def get_table_info_by_id(self, id: str) -> TableInfo | None:
        """按表 id 查询表元数据，最终组装成提示词里的表结构信息"""

        table_info: TableInfoMySQL | None = await self.session.get(TableInfoMySQL, id)
        if table_info:
            return TableInfoMapper.to_entity(table_info)
        else:
            return None

    async def get_key_columns_by_table_id(self, table_id: str) -> list[ColumnInfo]:
        """查询指定表的主外键字段，避免 Join 关键字段被向量召回漏掉"""

        # 主外键字段用于后续生成 join 条件，不能完全依赖向量召回命中
        sql = "select * from column_info where table_id = :table_id and role in ('primary_key','foreign_key')"
        # :table_id 是 SQLAlchemy text SQL 的占位符，实际值通过第二个参数传入
        result = await self.session.execute(text(sql), {"table_id": table_id})
        # mappings() 会把结果行转成类似字典的结构，便于解包成 ColumnInfo
        return [ColumnInfo(**dict(row)) for row in result.mappings().fetchall()]
