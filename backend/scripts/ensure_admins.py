"""Make sure the bootstrap admin emails exist and are active (run at deploy).

    BOOTSTRAP_ADMIN_EMAILS=a@x.org,b@y.org python -m scripts.ensure_admins

Admins added or removed in the app are left alone: this only creates or
re-activates the listed emails. The pre-Access password admin (an admin row
with no email) is deactivated, since nothing can sign in as it any more.
"""

from __future__ import annotations

import sys

from common.config import get_settings
from common.db import cursor
from common.logging_setup import get_logger, setup_logging

log = get_logger(__name__)


def main() -> int:
    setup_logging()
    emails = get_settings().bootstrap_admin_emails
    if not emails:
        log.error("BOOTSTRAP_ADMIN_EMAILS is empty; refusing to leave the site without an admin")
        return 1
    with cursor() as cur:
        for email in emails:
            cur.execute("SELECT user_id, role FROM app_user WHERE lower(email) = %s", (email,))
            row = cur.fetchone()
            if row is None:
                cur.execute(
                    "INSERT INTO app_user (email, name, role, daily_token_budget) "
                    "VALUES (%s, %s, 'admin', 0)", (email, email.split("@")[0]))
                log.info("admin created")
            elif row["role"] != "admin":
                log.error("an email in BOOTSTRAP_ADMIN_EMAILS belongs to a %s account", row["role"])
                return 1
            else:
                cur.execute("UPDATE app_user SET is_active = true WHERE user_id = %s",
                            (row["user_id"],))
        cur.execute("UPDATE app_user SET is_active = false "
                    "WHERE role = 'admin' AND email IS NULL AND is_active")
        if cur.rowcount:
            log.info("deactivated %d password-era admin account(s)", cur.rowcount)
    log.info("%d bootstrap admin(s) ready", len(emails))
    return 0


if __name__ == "__main__":
    sys.exit(main())
