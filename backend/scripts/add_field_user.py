"""Create field representatives ('rep', migration 0031) for the field-service Telegram bot.

    python -m scripts.add_field_user --name "रमेश कुमार"
    python -m scripts.add_field_user --name "सीता देवी" --phone 9000000001 --block 3
    python -m scripts.add_field_user --list

A rep is an app_user with role 'rep' and NO password: /login can never succeed for
one, and the API refuses a rep token (api/deps.py current_user). Reps only use the
bot. The printed user_id is what the field Team screen's "Import CSV" (or
POST /acs/{n}/field/members) takes as the member's core user id.

--phone is optional. When given it is the key: running again with the same phone
updates that rep's name and block instead of adding a second one. It never turns
an existing admin, strategist or block user into a rep.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.db import query, query_one  # noqa: E402


class RefusedError(Exception):
    """The request would change a user who is not a rep, or would duplicate one."""


def add_rep(name: str, phone: str | None = None, block_id: int | None = None,
            *, q1=query_one) -> tuple[int, bool]:
    """Create (or, by phone, update) a rep. Returns (user_id, created)."""
    name = name.strip()
    phone = (phone or "").strip() or None
    if not name:
        raise RefusedError("name is empty")
    if block_id is not None and q1("SELECT 1 AS ok FROM block WHERE block_id = %s", (block_id,)) is None:
        raise RefusedError(f"no block {block_id}")

    if phone is not None:
        existing = q1("SELECT user_id, role FROM app_user WHERE phone = %s", (phone,))
        if existing is not None:
            if existing["role"] != "rep":
                raise RefusedError(f"phone {phone} belongs to user {existing['user_id']} "
                                   f"(role {existing['role']}); a web user is never turned into a rep")
            # no --block keeps the block the rep already has; it never silently clears it
            q1("UPDATE app_user SET name = %s, block_id = COALESCE(%s, block_id), is_active = true "
               "WHERE user_id = %s RETURNING user_id", (name, block_id, existing["user_id"]))
            return existing["user_id"], False
    else:
        same = q1("SELECT user_id FROM app_user WHERE role = 'rep' AND is_active AND phone IS NULL "
                  "AND name = %s", (name,))
        if same is not None:
            raise RefusedError(f"an active rep named {name!r} already exists (user {same['user_id']}); "
                               "give --phone to tell two people with the same name apart")

    row = q1("INSERT INTO app_user (phone, name, role, block_id, password_hash, daily_token_budget) "
             "VALUES (%s, %s, 'rep', %s, NULL, 0) RETURNING user_id", (phone, name, block_id))
    return row["user_id"], True


def list_reps(*, q=query) -> list[dict]:
    return q("SELECT user_id, name, phone, block_id, is_active FROM app_user "
             "WHERE role = 'rep' ORDER BY user_id")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Create field representatives (bot-only users)")
    ap.add_argument("--name", help="the rep's name, as the team should see it")
    ap.add_argument("--phone", help="optional; makes re-running update this rep instead of adding another")
    ap.add_argument("--block", type=int, help="optional block_id to hold the rep to")
    ap.add_argument("--list", action="store_true", help="list every rep and exit")
    args = ap.parse_args(argv)

    if args.list:
        rows = list_reps()
        if not rows:
            print("No reps yet.")
        for r in rows:
            print(f"{r['user_id']:>6}  {r['name']}  phone={r['phone'] or '-'}  block={r['block_id'] or '-'}"
                  f"{'' if r['is_active'] else '  (inactive)'}")
        return 0
    if not args.name:
        ap.error("--name is required (or use --list)")

    try:
        user_id, created = add_rep(args.name, args.phone, args.block)
    except RefusedError as e:
        print(f"Refused: {e}", file=sys.stderr)
        return 2
    print(f"{'Created' if created else 'Updated'} rep {args.name.strip()!r}: user_id {user_id}")
    print("Add them to the field team with this user_id (Team screen > Import CSV).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
