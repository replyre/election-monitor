"""The 'rep' role (0031): field representatives exist in app_user for the
field-service Telegram bot, but must never use this API.

scoped_block_id treats every non-'block' role as unrestricted, so a rep that
got past current_user would see every block. current_user refuses one even
with a validly signed token.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from api import deps

SECRET = "x" * 8 + "Q7v2Lm9Pz4Rk8Ws1Tn6Yb3Hc5Jd0Fg"   # long, mixed: passes nothing but this test


@pytest.fixture
def as_user(monkeypatch):
    """Make current_user resolve the token's subject to a row with the given role."""
    settings = dataclasses.replace(deps.get_settings(), jwt_secret=SECRET, jwt_algorithm="HS256")
    monkeypatch.setattr(deps, "get_settings", lambda: settings)

    def _as(role: str, block_id: int | None = None):
        row = {"user_id": 7, "name": "Test", "role": role, "block_id": block_id,
               "daily_token_budget": 1000}
        monkeypatch.setattr(deps, "query_one", lambda sql, params=None: row)
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=deps.make_token(7, role))
        return deps.current_user(creds)

    return _as


def test_a_rep_token_is_refused_even_when_validly_signed(as_user):
    with pytest.raises(HTTPException) as e:
        as_user("rep")
    assert e.value.status_code == 403


@pytest.mark.parametrize("role,block_id", [("admin", None), ("strategist", None), ("block", 3)])
def test_web_roles_are_still_accepted(as_user, role, block_id):
    assert as_user(role, block_id).role == role


def test_rep_is_a_known_role_but_not_a_web_role():
    assert "rep" in deps.ROLES
    assert "rep" not in deps.WEB_ROLES
    assert set(deps.WEB_ROLES) == set(deps.ROLES) - {"rep"}


def test_the_migration_allows_rep_in_the_role_check():
    sql = (Path(__file__).resolve().parents[1] / "db" / "migrations" / "0031_rep_role.sql").read_text("utf-8")
    assert "'rep'" in sql and "app_user_role_check" in sql
