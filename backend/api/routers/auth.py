"""Authentication.

The site is public and read-only; nobody signs in to read it. Admins reach the
admin hostname through Cloudflare Access, which proves the email address with a
one-time code at the edge and forwards a signed assertion. POST /auth/access
verifies that assertion and, for an email belonging to an active admin, returns
an app token. Password login exists only outside production (local development
and the test suites): `password_router` is not mounted when APP_ENV=production.
"""

from __future__ import annotations

import functools
import secrets

import jwt
from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field

from api.deps import CurrentUser, make_token, verify_password
from common.config import get_settings
from common.db import execute, query_one
from common.logging_setup import get_logger

log = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])
password_router = APIRouter(prefix="/auth", tags=["auth"])


class PasswordLogin(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    name: str
    block_id: int | None = None


def _team_url(team_domain: str) -> str:
    host = team_domain.removeprefix("https://").rstrip("/")
    if "." not in host:
        host = f"{host}.cloudflareaccess.com"
    return f"https://{host}"


@functools.lru_cache(maxsize=4)
def _jwks_client(certs_url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(certs_url, cache_keys=True, lifespan=3600, timeout=10)


def access_email(assertion: str) -> str | None:
    """The verified email in a Cloudflare Access assertion, or None.

    Signature (RS256, the team's published keys), audience, issuer and expiry
    are all checked; anything else - a forged, expired or other-app token -
    is None, never an exception.
    """
    s = get_settings()
    team = _team_url(s.cf_access_team_domain)
    try:
        key = _jwks_client(f"{team}/cdn-cgi/access/certs").get_signing_key_from_jwt(assertion)
        claims = jwt.decode(assertion, key.key, algorithms=["RS256"], audience=s.cf_access_aud,
                            issuer=team, options={"require": ["exp", "iat", "aud", "iss"]})
    except (jwt.PyJWTError, OSError) as exc:
        log.info("rejected an Access assertion (%s)", type(exc).__name__)
        return None
    email = claims.get("email")
    return email.strip().lower() if isinstance(email, str) and "@" in email else None


@router.post("/access", response_model=Token)
def access(cf_access_jwt_assertion: str | None = Header(default=None)) -> Token:
    s = get_settings()
    if not (s.cf_access_team_domain and s.cf_access_aud):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Admin sign-in is not configured")
    if not cf_access_jwt_assertion:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Open the admin address to sign in")
    email = access_email(cf_access_jwt_assertion)
    if email is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "The sign-in could not be verified")
    user = query_one(
        "SELECT user_id, name, role, block_id FROM app_user "
        "WHERE lower(email) = %s AND is_active AND role = 'admin'",
        (email,),
    )
    if user is None:
        log.info("Access sign-in by an email that is not an admin")
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This email does not have admin access")
    execute("UPDATE app_user SET last_login_at = now() WHERE user_id = %s", (user["user_id"],))
    return Token(access_token=make_token(user["user_id"], user["role"], s.admin_token_ttl_minutes),
                 role=user["role"], name=user["name"], block_id=user["block_id"])


@password_router.post("/login", response_model=Token)
def login(body: PasswordLogin) -> Token:
    settings = get_settings()
    if settings.auth_mode != "password":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Password login is disabled")
    expected = "" if settings.allow_multi_user else (settings.app_username or "").strip()
    if expected and not secrets.compare_digest(body.username.strip(), expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect user id or password")
    user = query_one(
        "SELECT user_id, name, role, block_id, password_hash FROM app_user "
        "WHERE is_active AND (username = %s OR (%s = '' AND phone = %s))",
        (body.username.strip(), expected, body.username.strip()),
    )
    if user is None or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect user id or password")

    execute("UPDATE app_user SET last_login_at = now() WHERE user_id = %s", (user["user_id"],))
    return Token(access_token=make_token(user["user_id"], user["role"]),
                 role=user["role"], name=user["name"], block_id=user["block_id"])


@router.get("/me")
def me(user: CurrentUser) -> dict:
    return {
        "user_id": user.user_id, "name": user.name, "role": user.role,
        "block_id": user.block_id, "sees_caste": user.sees_caste,
        "daily_token_budget": user.daily_token_budget,
    }
