"""
Database-Native Atomic Upsert Utilities.
Provides race-safe, concurrent ON CONFLICT DO NOTHING semantics for PostgreSQL and SQLite.
"""
from typing import Any, Dict, List, Type
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert


async def atomic_insert_on_conflict_do_nothing(
    db: AsyncSession,
    model: Type[Any],
    values: Dict[str, Any],
    index_elements: List[str],
) -> None:
    """
    Executes a database-level atomic INSERT ... ON CONFLICT (index_elements) DO NOTHING.
    Guarantees race-safe concurrency across multiple workers without relying on
    non-atomic application-level SELECT-then-INSERT checks.
    """
    bind = db.bind
    dialect_name = bind.dialect.name if bind is not None else "sqlite"

    if dialect_name == "postgresql":
        stmt = pg_insert(model).values(**values).on_conflict_do_nothing(index_elements=index_elements)
    else:
        stmt = sqlite_insert(model).values(**values).on_conflict_do_nothing(index_elements=index_elements)

    await db.execute(stmt)
