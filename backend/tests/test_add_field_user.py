"""scripts/add_field_user.py: creating bot-only field representatives.

No database (see conftest): a tiny in-memory app_user stands behind the one
query function add_rep uses.
"""
from __future__ import annotations

import pytest

from scripts.add_field_user import RefusedError, add_rep


class FakeCore:
    def __init__(self):
        self.users: dict[int, dict] = {
            1: {"user_id": 1, "name": "Candidate", "phone": "9000000000", "role": "admin",
                "block_id": None, "password_hash": "$2b$x", "is_active": True},
        }
        self.blocks = {3}

    def q1(self, sql: str, params=()):
        s = " ".join(sql.split())
        if s.startswith("SELECT 1 AS ok FROM block"):
            return {"ok": 1} if params[0] in self.blocks else None
        if s.startswith("SELECT user_id, role FROM app_user WHERE phone"):
            u = next((u for u in self.users.values() if u["phone"] == params[0]), None)
            return None if u is None else {"user_id": u["user_id"], "role": u["role"]}
        if s.startswith("SELECT user_id FROM app_user WHERE role = 'rep'"):
            u = next((u for u in self.users.values() if u["role"] == "rep" and u["is_active"]
                      and u["phone"] is None and u["name"] == params[0]), None)
            return None if u is None else {"user_id": u["user_id"]}
        if s.startswith("UPDATE app_user SET name"):
            name, block_id, uid = params
            assert "COALESCE" in s, "an omitted block keeps the existing one"
            self.users[uid].update(name=name, is_active=True,
                                   block_id=block_id if block_id is not None else self.users[uid]["block_id"])
            return {"user_id": uid}
        if s.startswith("INSERT INTO app_user"):
            phone, name, block_id = params
            assert "'rep'" in s and "NULL" in s, "a rep is inserted with role rep and no password"
            uid = max(self.users) + 1
            self.users[uid] = {"user_id": uid, "name": name, "phone": phone, "role": "rep",
                               "block_id": block_id, "password_hash": None, "is_active": True}
            return {"user_id": uid}
        raise AssertionError(f"unexpected SQL: {s}")


@pytest.fixture
def core():
    return FakeCore()


def test_a_rep_is_created_without_a_password(core):
    uid, created = add_rep("रमेश कुमार", q1=core.q1)
    assert created
    u = core.users[uid]
    assert u["role"] == "rep" and u["password_hash"] is None and u["block_id"] is None


def test_a_rep_can_be_held_to_an_existing_block(core):
    uid, _ = add_rep("सीता देवी", block_id=3, q1=core.q1)
    assert core.users[uid]["block_id"] == 3


def test_an_unknown_block_is_refused(core):
    with pytest.raises(RefusedError, match="no block 99"):
        add_rep("X", block_id=99, q1=core.q1)


def test_the_same_phone_updates_the_rep_instead_of_adding_another(core):
    uid, created = add_rep("Old name", phone="9000000001", q1=core.q1)
    uid2, created2 = add_rep("New name", phone="9000000001", block_id=3, q1=core.q1)
    assert created and not created2 and uid == uid2
    assert core.users[uid]["name"] == "New name" and core.users[uid]["block_id"] == 3
    assert sum(u["role"] == "rep" for u in core.users.values()) == 1


def test_updating_without_a_block_keeps_the_existing_block(core):
    uid, _ = add_rep("Sita", phone="9000000004", block_id=3, q1=core.q1)
    add_rep("Sita Devi", phone="9000000004", q1=core.q1)
    assert core.users[uid]["name"] == "Sita Devi" and core.users[uid]["block_id"] == 3


def test_a_web_user_is_never_turned_into_a_rep(core):
    with pytest.raises(RefusedError, match="never turned into a rep"):
        add_rep("Someone", phone="9000000000", q1=core.q1)
    assert core.users[1]["role"] == "admin" and core.users[1]["password_hash"] == "$2b$x"


def test_two_reps_with_the_same_name_and_no_phone_are_refused(core):
    add_rep("Ram", q1=core.q1)
    with pytest.raises(RefusedError, match="already exists"):
        add_rep("Ram", q1=core.q1)


def test_same_name_is_fine_when_phones_tell_them_apart(core):
    a, _ = add_rep("Ram", phone="9000000002", q1=core.q1)
    b, _ = add_rep("Ram", phone="9000000003", q1=core.q1)
    assert a != b


def test_an_empty_name_is_refused(core):
    with pytest.raises(RefusedError, match="name is empty"):
        add_rep("   ", q1=core.q1)
