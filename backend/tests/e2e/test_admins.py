"""The admin email allow-list (api/routers/admins.py, migration 0034), end to end."""

from __future__ import annotations

import pytest

from api.deps import make_token
from tests.e2e.conftest import requires_db

pytestmark = requires_db


@pytest.fixture()
def admin_headers(conn, client, users):
    """An Access-style admin: an admin row with an email, as /auth/access issues."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO app_user (email, name, role, daily_token_budget) "
            "VALUES ('first-admin@example.org', 'First admin', 'admin', 0) "
            "ON CONFLICT (email) DO UPDATE SET is_active = true RETURNING user_id")
        user_id = cur.fetchone()["user_id"]
    yield {"Authorization": f"Bearer {make_token(user_id, 'admin')}"}, user_id
    with conn.cursor() as cur:
        cur.execute("DELETE FROM app_user WHERE email LIKE '%%@example.org'")


def test_an_admin_adds_lists_and_removes_another_admin(client, admin_headers):
    headers, _ = admin_headers
    r = client.post("/admins", headers=headers,
                    json={"email": "  Second.Admin@Example.org ", "name": "Second  admin"})
    assert r.status_code == 201, r.text
    added = r.json()
    assert added["email"] == "second.admin@example.org" and added["name"] == "Second admin"

    listed = client.get("/admins", headers=headers).json()["admins"]
    assert {a["email"] for a in listed if a["is_active"]} >= {
        "first-admin@example.org", "second.admin@example.org"}

    assert client.delete(f"/admins/{added['user_id']}", headers=headers).status_code == 200
    listed = {a["email"]: a for a in client.get("/admins", headers=headers).json()["admins"]}
    assert listed["second.admin@example.org"]["is_active"] is False

    # Adding the same email again re-activates the row rather than duplicating it.
    again = client.post("/admins", headers=headers,
                        json={"email": "second.admin@example.org", "name": "Second admin"})
    assert again.status_code == 201 and again.json()["user_id"] == added["user_id"]


def test_an_admin_cannot_remove_themselves_or_the_last_admin(client, admin_headers):
    headers, user_id = admin_headers
    assert client.delete(f"/admins/{user_id}", headers=headers).status_code == 409


def test_a_non_admin_email_cannot_be_promoted_by_adding_it(client, admin_headers, conn):
    headers, _ = admin_headers
    with conn.cursor() as cur:
        cur.execute("INSERT INTO app_user (email, name, role, daily_token_budget) "
                    "VALUES ('rep-person@example.org', 'Rep', 'rep', 0)")
    r = client.post("/admins", headers=headers,
                    json={"email": "rep-person@example.org", "name": "Rep"})
    assert r.status_code == 409


@pytest.mark.parametrize("email", ["no-at-sign", "a@b", "x@" + "y" * 250 + ".com"])
def test_malformed_emails_are_refused(client, admin_headers, email):
    headers, _ = admin_headers
    assert client.post("/admins", headers=headers,
                       json={"email": email, "name": "X"}).status_code == 422


def test_only_admins_reach_the_list(client, tokens):
    assert client.get("/admins").status_code == 401
    for role in ("strategist", "block"):
        r = client.get("/admins", headers={"Authorization": f"Bearer {tokens[role]}"})
        assert r.status_code == 403
