"""Who has admin access: the email allow-list, managed by admins.

An admin is an active app_user with role 'admin' and an email. Cloudflare Access
proves the email at the edge; /auth/access then admits it only if it is listed
here. Removing an admin deactivates the row, so their audit trail keeps its name.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from api.deps import AdminUser
from common.db import cursor, query, query_one

router = APIRouter(prefix="/admins", tags=["admins"])

_EMAIL = re.compile(r"^[^@\s]{1,64}@[A-Za-z0-9.-]{1,189}\.[A-Za-z]{2,24}$")


class NewAdmin(BaseModel):
    email: str = Field(min_length=6, max_length=254)
    name: str = Field(min_length=1, max_length=80)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL.match(v):
            raise ValueError("not an email address")
        return v

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("name is required")
        return v


@router.get("")
def list_admins(user: AdminUser) -> dict:
    rows = query(
        "SELECT user_id, name, lower(email) AS email, is_active, last_login_at FROM app_user "
        "WHERE role = 'admin' AND email IS NOT NULL ORDER BY is_active DESC, lower(email)"
    )
    return {"admins": rows}


@router.post("", status_code=201)
def add_admin(body: NewAdmin, user: AdminUser) -> dict:
    existing = query_one(
        "SELECT user_id, role, is_active FROM app_user WHERE lower(email) = %s", (body.email,))
    if existing is not None and existing["role"] != "admin":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "This email belongs to a non-admin account")
    with cursor() as cur:
        if existing is None:
            cur.execute(
                "INSERT INTO app_user (email, name, role, daily_token_budget) "
                "VALUES (%s, %s, 'admin', 0) RETURNING user_id",
                (body.email, body.name),
            )
            user_id = cur.fetchone()["user_id"]
        else:
            user_id = existing["user_id"]
            cur.execute("UPDATE app_user SET is_active = true, name = %s WHERE user_id = %s",
                        (body.name, user_id))
    return {"user_id": user_id, "email": body.email, "name": body.name, "is_active": True}


@router.delete("/{user_id}")
def remove_admin(user_id: int, user: AdminUser) -> dict:
    if user_id == user.user_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "You cannot remove your own admin access")
    with cursor() as cur:
        # Serialise removals so two admins removing each other cannot leave none.
        cur.execute("SELECT pg_advisory_xact_lock(hashtext('admins'))")
        cur.execute(
            "SELECT COUNT(*) AS n FROM app_user WHERE role = 'admin' AND is_active "
            "AND email IS NOT NULL AND user_id <> %s", (user_id,))
        if cur.fetchone()["n"] == 0:
            raise HTTPException(status.HTTP_409_CONFLICT, "At least one admin must remain")
        cur.execute(
            "UPDATE app_user SET is_active = false WHERE user_id = %s AND role = 'admin' "
            "AND email IS NOT NULL", (user_id,))
        if cur.rowcount == 0:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such admin")
    return {"user_id": user_id, "is_active": False}
