"""CoreDbAdapter against a minimal copy of the core's tables (app_user, ac, block).

The core's role check is the one after its migration 0033_rep_role.sql: admin | strategist | block | rep.
Only get_user and verify_token are exercised here; the geography reads are covered by the
conformance suite when it is pointed at a real core database.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import jwt
import psycopg
import pytest

from pulse.core_adapter.core import CoreDbAdapter

SECRET = "core-test-secret-" + "k" * 32

CORE_SCHEMA = """
CREATE TABLE ac (ac_id SMALLINT PRIMARY KEY, ac_number SMALLINT UNIQUE NOT NULL,
                 name_en TEXT NOT NULL, name_hi TEXT NOT NULL, is_active BOOLEAN NOT NULL DEFAULT true);
CREATE TABLE block (block_id SMALLINT PRIMARY KEY, ac_id SMALLINT NOT NULL REFERENCES ac(ac_id),
                    name_en TEXT NOT NULL, name_hi TEXT NOT NULL);
CREATE TABLE app_user (
    user_id   SERIAL PRIMARY KEY,
    name      TEXT NOT NULL,
    role      TEXT NOT NULL CONSTRAINT app_user_role_check CHECK (role IN ('admin', 'strategist', 'block', 'rep')),
    block_id  SMALLINT REFERENCES block(block_id),
    is_active BOOLEAN NOT NULL DEFAULT true,
    CONSTRAINT block_user_needs_block CHECK (role <> 'block' OR block_id IS NOT NULL));
INSERT INTO ac VALUES (1, 32, 'Giridih', 'गिरिडीह', true), (2, 31, 'Gandey', 'गांडेय', true);
INSERT INTO block VALUES (10, 1, 'Giridih', 'गिरिडीह'), (20, 2, 'Gandey', 'गांडेय');
INSERT INTO app_user (user_id, name, role, block_id, is_active) VALUES
    (1, 'Candidate',          'admin', NULL, true),
    (2, 'Rep, no block',      'rep',   NULL, true),
    (3, 'Rep in block 10',    'rep',   10,   true),
    (4, 'Block user',         'block', 20,   true),
    (5, 'Inactive rep',       'rep',   NULL, false);
"""


@pytest.fixture(scope="module")
def core_url(database_url):
    admin_url = re.sub(r"/[^/]+$", "/postgres", database_url)
    url = re.sub(r"/[^/]+$", "/core_adapter_test", database_url)
    with psycopg.connect(admin_url, autocommit=True) as a:
        a.execute("DROP DATABASE IF EXISTS core_adapter_test")
        a.execute("CREATE DATABASE core_adapter_test")
    with psycopg.connect(url, autocommit=True) as c:
        c.execute(CORE_SCHEMA)
    yield url
    with psycopg.connect(admin_url, autocommit=True) as a:
        a.execute("DROP DATABASE IF EXISTS core_adapter_test WITH (FORCE)")


@pytest.fixture(scope="module")
def adapter(core_url):
    a = CoreDbAdapter(core_url, SECRET)
    yield a
    a.close()


def _token(sub: str, secret: str = SECRET, minutes: int = 10) -> str:
    return jwt.encode({"sub": sub, "exp": datetime.now(timezone.utc) + timedelta(minutes=minutes)},
                      secret, algorithm="HS256")


def test_a_rep_without_a_block_spans_the_active_acs(adapter):
    u = adapter.get_user("2")
    assert u is not None and u.role == "rep"
    assert set(u.ac_ids) == {"ac-31", "ac-32"}
    assert u.block_ids == ()


def test_a_rep_with_a_block_is_held_to_it(adapter):
    u = adapter.get_user("3")
    assert u.role == "rep" and u.ac_ids == ("ac-32",) and u.block_ids == ("10",)


def test_block_and_admin_users_are_unchanged(adapter):
    b = adapter.get_user("4")
    assert b.role == "block" and b.ac_ids == ("ac-31",) and b.block_ids == ("20",)
    a = adapter.get_user("1")
    assert a.role == "admin" and set(a.ac_ids) == {"ac-31", "ac-32"} and a.block_ids == ()


def test_an_inactive_rep_is_not_a_user(adapter):
    assert adapter.get_user("5") is None


def test_a_rep_token_from_the_core_verifies(adapter):
    """The core signs {"sub": user_id, "role", "exp"} with HS256 (backend/api/deps.py make_token)."""
    u = adapter.verify_token(_token("2"))
    assert u is not None and u.user_id == "2" and u.role == "rep"


def test_a_token_signed_with_another_secret_is_refused(adapter):
    assert adapter.verify_token(_token("2", secret="not-the-core-secret-" + "z" * 30)) is None


def test_an_expired_token_is_refused(adapter):
    assert adapter.verify_token(_token("2", minutes=-1)) is None


def test_the_adapter_cannot_write_to_the_core(adapter):
    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        adapter._rows("UPDATE app_user SET name = 'x' WHERE user_id = 2")
