"""giridih_app (0032) can do what the API does and nothing else."""

from __future__ import annotations

import pytest

from tests.e2e.conftest import API_ROLE_PASSWORD, api_role_url

psycopg = pytest.importorskip("psycopg")
errors = pytest.importorskip("psycopg.errors")


@pytest.fixture(scope="module")
def app_conn(conn, db_url, users):
    with conn.cursor() as cur:
        cur.execute(f"ALTER ROLE giridih_app LOGIN PASSWORD '{API_ROLE_PASSWORD}'")
    c = psycopg.connect(api_role_url(db_url), autocommit=True)
    yield c
    c.close()


@pytest.mark.parametrize("sql", [
    "SELECT COUNT(*) FROM mv_ac_summary",
    "SELECT COUNT(*) FROM booth",
    "SELECT password_hash FROM app_user LIMIT 1",
    "UPDATE app_user SET last_login_at = now() WHERE false",
    "UPDATE review_queue SET status = 'open' WHERE false",
])
def test_what_the_api_needs_is_allowed(app_conn, sql):
    app_conn.execute(sql)


@pytest.mark.parametrize("sql", [
    "UPDATE app_user SET password_hash = 'x' WHERE false",
    "UPDATE app_user SET role = 'admin' WHERE false",
    "INSERT INTO app_user (phone, name, role) VALUES ('1', 'x', 'admin')",
    "DELETE FROM booth WHERE false",
    "UPDATE result_booth SET votes = 0 WHERE false",
    "TRUNCATE news_item",
    "DROP TABLE booth",
    "CREATE TABLE pwned (id int)",
    "REFRESH MATERIALIZED VIEW mv_ac_summary",
])
def test_everything_else_is_refused(app_conn, sql):
    with pytest.raises((errors.InsufficientPrivilege, errors.WrongObjectType)):
        app_conn.execute(sql)


def test_the_chat_role_cannot_sign_in(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT rolcanlogin FROM pg_roles WHERE rolname = 'giridih_ro'")
        row = cur.fetchone()
    assert row is None or row["rolcanlogin"] is False
