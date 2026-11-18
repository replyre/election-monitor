"""Postgres access helpers (psycopg 3) over one application pool."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator, Sequence
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.numeric import FloatLoader
from psycopg_pool import ConnectionPool

from common.config import get_settings
from common.logging_setup import get_logger

log = get_logger(__name__)

_pool: ConnectionPool | None = None


def _configure(conn: psycopg.Connection) -> None:
    """Load NUMERIC as float on every pooled connection.

    psycopg's default is `decimal.Decimal`, and FastAPI (pydantic 2) serialises a
    Decimal as a JSON *string*, so margin_pct, turnout_pct, priority_score and
    every other NUMERIC column reached the browser as "25.29" and the frontend's
    `value.toFixed()` threw on it. The values are percentages, shares and scores
    already rounded in SQL, well inside float precision; no code here relies on
    Decimal semantics. tests/e2e/test_api_json_types.py pins this.
    """
    conn.adapters.register_loader("numeric", FloatLoader)


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        s = get_settings()
        if not s.database_url:
            raise RuntimeError("DATABASE_URL is not set")
        _pool = ConnectionPool(
            s.database_url,
            min_size=s.db_pool_min,
            max_size=max(s.db_pool_max, s.db_pool_min),
            # A request should fail fast rather than queue for minutes behind a
            # stuck connection.
            timeout=15,
            max_idle=300,
            # Verify a connection before handing it out: a pooler restart or a
            # dropped NAT mapping otherwise surfaces as a 500 on the next request.
            check=ConnectionPool.check_connection,
            kwargs={
                "row_factory": dict_row,
                "connect_timeout": 10,
                # Cloud NATs drop idle TCP flows after ~4 minutes (Azure's default);
                # keepalives stop idle pooled connections dying silently.
                "keepalives": 1,
                "keepalives_idle": 60,
                "keepalives_interval": 15,
                "keepalives_count": 4,
            },
            configure=_configure,
            open=True,
        )
    return _pool


def close_pools() -> None:
    global _pool
    if _pool is not None:
        with contextlib.suppress(Exception):
            _pool.close()
    _pool = None


@contextlib.contextmanager
def connection() -> Iterator[psycopg.Connection]:
    with get_pool().connection() as conn:
        yield conn


@contextlib.contextmanager
def cursor() -> Iterator[psycopg.Cursor]:
    with connection() as conn, conn.cursor() as cur:
        yield cur


def query(sql: str, params: Sequence[Any] | dict[str, Any] | None = None) -> list[dict[str, Any]]:
    with cursor() as cur:
        cur.execute(sql, params)
        if cur.description is None:
            return []
        return cur.fetchall()


def query_one(sql: str, params: Sequence[Any] | dict[str, Any] | None = None) -> dict[str, Any] | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: Sequence[Any] | dict[str, Any] | None = None) -> int:
    with cursor() as cur:
        cur.execute(sql, params)
        return cur.rowcount


def executemany(sql: str, rows: Sequence[Sequence[Any]]) -> int:
    if not rows:
        return 0
    with cursor() as cur:
        cur.executemany(sql, rows)
        return cur.rowcount


def copy_rows(table: str, columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> int:
    """Bulk load via COPY. Used by the Form 20 and roll loaders."""
    if not rows:
        return 0
    cols = ", ".join(columns)
    with cursor() as cur:
        with cur.copy(f"COPY {table} ({cols}) FROM STDIN") as cp:
            for row in rows:
                cp.write_row(row)
        return len(rows)
