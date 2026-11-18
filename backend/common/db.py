"""Postgres access helpers (psycopg 3) over one application pool."""

from __future__ import annotations

import contextlib
import re
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
            # Recycle idle connections before a pooler or NAT idle limit closes
            # them underneath us; reads that still hit a dead one are retried.
            max_idle=180,
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


_READ = re.compile(r"^\s*(SELECT|WITH)\b", re.I)


def query(sql: str, params: Sequence[Any] | dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """One statement in autocommit: no BEGIN/COMMIT round trips, which were half
    the cost of every read. A read on a connection the server or a NAT dropped is
    retried once on a fresh one; anything else is not, so a write never runs twice."""
    for attempt in (1, 2):
        try:
            with get_pool().connection() as conn:
                conn.autocommit = True
                try:
                    with conn.cursor() as cur:
                        cur.execute(sql, params)
                        return cur.fetchall() if cur.description is not None else []
                finally:
                    if not conn.closed:
                        conn.autocommit = False
        except psycopg.OperationalError:
            if attempt == 2 or not _READ.match(sql):
                raise
            log.warning("read hit a dropped database connection; retrying once")
    raise AssertionError("unreachable")


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
