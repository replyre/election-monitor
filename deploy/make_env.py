#!/usr/bin/env python3
"""Write deploy/env/{api,jobs,cloudflared}.env from a source .env, printing no values.

    python3 deploy/make_env.py ../giridih-monitor/.env [--hostname app.example.com]

The jobs keep DATABASE_URL (the owner: they refresh views and run migrations).
The API connects as giridih_app (0032), the field service as pulse_app and
pulse_core_ro (0035), each with a generated password that the deploy's
migration step sets, so they always match. A fresh JWT_SECRET is generated
unless --keep-jwt is given; a new one signs every admin out. TELEGRAM_* in the
source produce pulse.env, TUNNEL_TOKEN produces cloudflared.env, and
BOOTSTRAP_ADMIN_EMAILS (required) seeds the admin allow-list.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

HERE = Path(__file__).resolve().parent


def parse(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key.strip()] = value
    return out


def write(path: Path, values: dict[str, str]) -> None:
    for key, value in values.items():
        if "\n" in value:
            sys.exit(f"{key} contains a newline")
    path.parent.mkdir(mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.writelines(f"{k}={v}\n" for k, v in values.items())
    print(f"wrote {path.name} ({', '.join(values)})")


def with_sslmode(url: str) -> str:
    return url if "sslmode=" in url else url + ("&" if "?" in url else "?") + "sslmode=require"


def as_role(url: str, role: str, password: str) -> str:
    """The same server, signed in as `role`. Supabase's pooler names the project
    after the role (postgres.<ref> -> giridih_app.<ref>); a direct URL does not."""
    parts = urlsplit(url)
    user = parts.username or ""
    new_user = role + user[user.index("."):] if "." in user else role
    host = parts.hostname or ""
    netloc = f"{quote(new_user, safe='')}:{quote(password, safe='')}@{host}"
    if parts.port:
        netloc += f":{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path)
    ap.add_argument("--hostname", default="", help="public hostname, e.g. example.org")
    ap.add_argument("--keep-jwt", action="store_true")
    ap.add_argument("--out", type=Path, default=HERE / "env")
    args = ap.parse_args()

    src = parse(args.source)
    for key in ("DATABASE_URL", "BOOTSTRAP_ADMIN_EMAILS"):
        if not src.get(key):
            sys.exit(f"{key} is missing from {args.source}")

    jwt = src["JWT_SECRET"] if args.keep_jwt and src.get("JWT_SECRET") else secrets.token_hex(64)
    db_url = with_sslmode(src["DATABASE_URL"])
    passwords = {role: secrets.token_urlsafe(32) for role in ("giridih_app", "pulse_app", "pulse_core_ro")}
    role_url = {role: with_sslmode(as_role(src["DATABASE_URL"], role, pw)) for role, pw in passwords.items()}
    public = f"https://{args.hostname}" if args.hostname else "http://127.0.0.1:8080"
    admin_url = src.get("ADMIN_URL") or (f"https://admin.{args.hostname}" if args.hostname else "")

    common = {"TZ": "Asia/Kolkata", "LOG_LEVEL": src.get("LOG_LEVEL", "INFO")}
    write(args.out / "api.env", {
        **common,
        "APP_ENV": "production",
        "DATABASE_URL": role_url["giridih_app"],
        "DB_POOL_MIN": "4",
        "DB_POOL_MAX": "6",
        "AC_CACHE_SECONDS": "300",
        "JWT_SECRET": jwt,
        "JWT_ALGORITHM": "HS256",
        "JWT_TTL_MINUTES": src.get("JWT_TTL_MINUTES", "720"),
        "API_CORS_ORIGINS": ",".join(o for o in (public, admin_url) if o),
        "ADMIN_URL": admin_url,
        "CF_ACCESS_TEAM_DOMAIN": src.get("CF_ACCESS_TEAM_DOMAIN", ""),
        "CF_ACCESS_AUD": src.get("CF_ACCESS_AUD", ""),
    })
    write(args.out / "jobs.env", {
        **common,
        "APP_ENV": "production",
        "DATABASE_URL": db_url,
        "DB_POOL_MIN": "0",
        "DB_POOL_MAX": "2",
        "BOOTSTRAP_ADMIN_EMAILS": src["BOOTSTRAP_ADMIN_EMAILS"],
        "API_DB_PASSWORD": passwords["giridih_app"],
        "PULSE_DB_PASSWORD": passwords["pulse_app"],
        "PULSE_CORE_RO_PASSWORD": passwords["pulse_core_ro"],
        "BACKUP_DIR": "/data/backups",
        "BACKUP_RETENTION_DAYS": "14",
        "RAW_DIR": "/tmp/raw",
        "OCR_DIR": "/tmp/ocr",
    })
    if all(src.get(k) for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_USERNAME", "TELEGRAM_WEBHOOK_SECRET")):
        write(args.out / "pulse.env", {
            "TZ": "Asia/Kolkata",
            "PULSE_ENV": "production",
            "DATABASE_URL": role_url["pulse_app"],
            "CORE_ADAPTER": "core",
            "CORE_DATABASE_URL": role_url["pulse_core_ro"],
            "CORE_JWT_SECRET": jwt,
            "JWT_SECRET": secrets.token_urlsafe(48),
            "TELEGRAM_BOT_TOKEN": src["TELEGRAM_BOT_TOKEN"],
            "TELEGRAM_BOT_USERNAME": src["TELEGRAM_BOT_USERNAME"].lstrip("@"),
            "TELEGRAM_WEBHOOK_SECRET": src["TELEGRAM_WEBHOOK_SECRET"],
            "BOT_MODE": "polling",
            "MEDIA_DIR": "/data/media",
            "MEDIA_RETENTION_DAYS": src.get("MEDIA_RETENTION_DAYS", "365"),
        })
    else:
        print("no TELEGRAM_* settings in the source: pulse.env not written (field service off)")
    if src.get("TUNNEL_TOKEN"):
        write(args.out / "cloudflared.env", {"TUNNEL_TOKEN": src["TUNNEL_TOKEN"]})
    return 0


if __name__ == "__main__":
    sys.exit(main())
