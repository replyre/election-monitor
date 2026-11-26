"""The field service's roles (0035): each can do its job and nothing else."""

from __future__ import annotations

import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from tests.e2e.conftest import requires_db

psycopg = pytest.importorskip("psycopg")
errors = pytest.importorskip("psycopg.errors")
pytestmark = requires_db

PASSWORD = "e2e-field-role-password-0123456789"


def _as(db_url: str, role: str) -> str:
    params = conninfo_to_dict(db_url)
    params.update(user=role, password=PASSWORD)
    return make_conninfo(**params)


@pytest.fixture(scope="module")
def roles(conn, db_url, loaded_dataset):
    with conn.cursor() as cur:
        for role in ("pulse_app", "pulse_core_ro"):
            cur.execute(f"ALTER ROLE {role} LOGIN PASSWORD '{PASSWORD}'")
    app = psycopg.connect(_as(db_url, "pulse_app"), autocommit=True)
    ro = psycopg.connect(_as(db_url, "pulse_core_ro"), autocommit=True)
    yield app, ro
    app.close()
    ro.close()
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS field.role_probe")


def test_pulse_app_owns_the_field_schema(roles, conn):
    app, _ = roles
    app.execute("CREATE TABLE field.role_probe (id int)")
    app.execute("INSERT INTO field.role_probe VALUES (1)")
    # The owner role still reads it, so the nightly pg_dump covers the field schema.
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM field.role_probe")
        assert cur.fetchone()["n"] == 1


@pytest.mark.parametrize("sql", [
    "SELECT * FROM public.app_user LIMIT 1",
    "SELECT * FROM public.booth LIMIT 1",
    "CREATE TABLE public.pwned (id int)",
    "UPDATE public.ac SET name_en = name_en WHERE false",
])
def test_pulse_app_cannot_touch_the_core(roles, sql):
    app, _ = roles
    with pytest.raises(errors.InsufficientPrivilege):
        app.execute(sql)


@pytest.mark.parametrize("sql", [
    "SELECT user_id, name, role, block_id FROM app_user WHERE is_active",
    "SELECT ac_number, name_en, name_hi FROM ac WHERE is_active",
    "SELECT block_id, name_en FROM block",
    "SELECT area_id, block_id, kind, name_en, name_hi FROM area",
    "SELECT booth_uid, area_id FROM booth WHERE is_active",
    "SELECT electors FROM roll_snapshot LIMIT 1",
    "SELECT revision_id, revision_date FROM roll_revision LIMIT 1",
])
def test_the_core_reader_reads_what_the_adapter_needs(roles, sql):
    _, ro = roles
    ro.execute(sql).fetchall()


def test_the_core_reader_sees_rows_despite_row_level_security(roles):
    _, ro = roles
    assert ro.execute("SELECT count(*) FROM ac").fetchone()[0] > 0


@pytest.mark.parametrize("sql, error", [
    ("SELECT password_hash FROM app_user", "InsufficientPrivilege"),
    ("SELECT phone, email FROM app_user", "InsufficientPrivilege"),
    ("SELECT * FROM field.role_probe", "InsufficientPrivilege"),
    ("SELECT * FROM result_booth LIMIT 1", "InsufficientPrivilege"),
    ("UPDATE ac SET name_en = name_en WHERE false", "ReadOnlySqlTransaction"),
    ("INSERT INTO block (block_id) VALUES (1)", "ReadOnlySqlTransaction"),
])
def test_the_core_reader_reads_nothing_else_and_writes_nothing(roles, sql, error):
    _, ro = roles
    with pytest.raises((errors.InsufficientPrivilege, errors.ReadOnlySqlTransaction)) as excinfo:
        ro.execute(sql)
    assert type(excinfo.value).__name__ == error


def test_0036_hands_owner_made_field_objects_to_pulse_app(conn, db_url, roles):
    """Field migrations once ran as the owner role; 0036 moves those objects
    to pulse_app without touching their rows."""
    from pathlib import Path

    app, _ = roles
    with conn.cursor() as cur:
        cur.execute("CREATE TABLE field.owner_made (id serial PRIMARY KEY, v text)")
        cur.execute("INSERT INTO field.owner_made (v) VALUES ('kept')")
        cur.execute("CREATE FUNCTION field.owner_fn() RETURNS int LANGUAGE sql AS 'SELECT 1'")
    with pytest.raises(errors.InsufficientPrivilege):
        app.execute("SELECT * FROM field.owner_made")
    sql = (Path(__file__).resolve().parents[2] / "db" / "migrations" / "0036_field_ownership.sql").read_text()
    with conn.cursor() as cur:
        cur.execute(sql)
    assert app.execute("SELECT v FROM field.owner_made").fetchone()[0] == "kept"
    app.execute("INSERT INTO field.owner_made (v) VALUES ('new')")
    assert app.execute("SELECT field.owner_fn()").fetchone()[0] == 1
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'field' AND pg_get_userbyid(c.relowner) <> 'pulse_app'")
        assert cur.fetchone()["n"] == 0
        cur.execute("DROP TABLE field.owner_made")
        cur.execute("DROP FUNCTION field.owner_fn()")
