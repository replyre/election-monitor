"""No request input ever reaches SQL text.

Every GET route is called with injection payloads in each string path segment
and each query parameter, against a fake connection pool that records the SQL
it is handed. A payload may appear among the bound parameters - that is where
it belongs - but never in the statement itself. Errors must not leak database
detail either.
"""

from __future__ import annotations

import re
import secrets
from contextlib import contextmanager

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

MARK = "zqx9"
PAYLOADS = [
    f"{MARK}' OR '1'='1",
    f"{MARK}'; DROP TABLE app_user;--",
    f"{MARK}\" OR 1=1 --",
    f"{MARK}) UNION SELECT password_hash FROM app_user--",
    f"{MARK}ʼ OR ʼ1ʼ=ʼ1",
    f"{MARK}" + "A" * 5000,
]


class _Cursor:
    def __init__(self, log: list[str]):
        self.log = log
        self.description = None
        self.rowcount = 0

    def execute(self, sql, params=None):
        self.log.append(sql if isinstance(sql, str) else repr(sql))

    def executemany(self, sql, rows):
        self.execute(sql)

    def fetchall(self):
        return []

    def fetchone(self):
        return None

    def __iter__(self):
        return iter(())

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Conn:
    closed = False
    autocommit = False

    def __init__(self, log):
        self.log = log

    def cursor(self, *a, **k):
        return _Cursor(self.log)

    def execute(self, sql, params=None):
        cur = _Cursor(self.log)
        cur.execute(sql, params)
        return cur

    def commit(self):
        pass

    def rollback(self):
        pass

    def transaction(self):
        return _null()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@contextmanager
def _null():
    yield


class _Pool:
    def __init__(self, log):
        self.log = log

    @contextmanager
    def connection(self, *a, **k):
        yield _Conn(self.log)


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", secrets.token_hex(32))
    from common.config import get_settings

    get_settings.cache_clear()
    import common.db as db
    from api import deps
    from api.main import app

    log: list[str] = []
    monkeypatch.setattr(db, "get_pool", lambda: _Pool(log))
    app.dependency_overrides[deps.current_user] = lambda: deps.User(
        user_id=1, name="t", role="admin", block_id=None, daily_token_budget=0)
    app.dependency_overrides[deps.current_ac] = lambda: deps.AC(
        ac_id=1, ac_number=32, name_en="Giridih", name_hi="गिरिडीह", reservation="GEN",
        verified=True, bypoll_due=None, vacancy_date=None)
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c, log
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def _get_routes():
    """Included routers are nested since FastAPI 0.141 (see test_api_topology)."""
    from api.main import app

    def walk(routes):
        for route in routes:
            nested = getattr(route, "original_router", None)
            if nested is not None:
                yield from walk(nested.routes)
            elif isinstance(route, APIRoute) and "GET" in route.methods:
                yield route

    yield from walk(app.routes)


def _requests(route: APIRoute):
    path_params = {p.name: p for p in route.dependant.path_params}
    query_params = [p.name for p in route.dependant.query_params]
    for payload in PAYLOADS:
        path = route.path
        for name, field in path_params.items():
            value = payload if field.field_info.annotation is str else "32"
            path = path.replace("{" + name + "}", value)
        yield path, {}
        for q in query_params:
            yield path.replace(payload, "x") if path_params else path, {q: payload}


def test_the_scan_covers_the_api():
    routes = list(_get_routes())
    assert len(routes) > 30
    assert sum(len(r.dependant.query_params) for r in routes) > 40


def test_no_payload_reaches_sql_text(client):
    c, log = client
    leaks, errors = [], []
    executed = 0
    for route in _get_routes():
        for path, params in _requests(route):
            log.clear()
            r = c.get(path, params=params)
            executed += len(log)
            for sql in log:
                if MARK in sql:
                    leaks.append(f"{route.path} {params or path}: {sql[:120]}")
            if r.status_code >= 500 and re.search(
                    r"psycopg|syntax|SELECT|relation|column", r.text, re.I):
                errors.append(f"{route.path}: {r.text[:200]}")
    assert executed > 500, f"only {executed} statements ran; the fake pool is not wired in"
    assert not leaks, "request input reached SQL text:\n" + "\n".join(leaks[:20])
    assert not errors, "a server error leaked database detail:\n" + "\n".join(errors[:20])
