"""The constituency lookup is cached only when AC_CACHE_SECONDS is set."""

from __future__ import annotations

import pytest

from api import deps
from common.config import get_settings

ROW = {"ac_id": 7, "ac_number": 32, "name_en": "Giridih", "name_hi": "गिरिडीह",
       "reservation": "GEN", "verified": True, "bypoll_due": None,
       "vacancy_date": None, "is_active": True}


@pytest.fixture()
def calls(monkeypatch):
    seen: list[int] = []

    def fake(sql, params):
        seen.append(params[0])
        return dict(ROW) if params[0] == 32 else None

    monkeypatch.setattr(deps, "query_one", fake)
    deps._ac_cache.clear()
    yield seen
    deps._ac_cache.clear()
    get_settings.cache_clear()


def test_off_by_default_every_request_reads(calls, monkeypatch):
    monkeypatch.delenv("AC_CACHE_SECONDS", raising=False)
    get_settings.cache_clear()
    deps._ac_row(32)
    deps._ac_row(32)
    assert calls == [32, 32]


def test_on_in_production_one_read_and_rows_are_not_shared(calls, monkeypatch):
    monkeypatch.setenv("AC_CACHE_SECONDS", "300")
    get_settings.cache_clear()
    first = deps._ac_row(32)
    first.pop("is_active")          # current_ac mutates its copy
    second = deps._ac_row(32)
    assert calls == [32]
    assert second["is_active"] is True
    assert deps._ac_row(99) is None and deps._ac_row(99) is None
    assert calls == [32, 99]


def test_entries_expire(calls, monkeypatch):
    monkeypatch.setenv("AC_CACHE_SECONDS", "300")
    get_settings.cache_clear()
    clock = iter([1000.0, 1000.0 + 301])
    monkeypatch.setattr(deps.time, "monotonic", lambda: next(clock))
    deps._ac_row(32)
    deps._ac_row(32)
    assert calls == [32, 32]
