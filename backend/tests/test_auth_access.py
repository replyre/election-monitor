"""POST /auth/access: a Cloudflare Access assertion in, an admin token out."""

from __future__ import annotations

import secrets
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

TEAM = "https://pulse-team.cloudflareaccess.com"
AUD = "a" * 64


def _key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


SIGNING = _key()
OTHER = _key()


def assertion(email="admin@example.org", aud=AUD, iss=TEAM, exp_in=600, key=SIGNING):
    now = int(time.time())
    return jwt.encode({"email": email, "aud": [aud], "iss": iss, "iat": now, "exp": now + exp_in,
                       "sub": "cf-user"}, key, algorithm="RS256", headers={"kid": "k1"})


class _Jwks:
    def get_signing_key_from_jwt(self, token):
        return type("K", (), {"key": SIGNING.public_key()})()


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", secrets.token_hex(32))
    monkeypatch.setenv("CF_ACCESS_TEAM_DOMAIN", "pulse-team")
    monkeypatch.setenv("CF_ACCESS_AUD", AUD)
    from common.config import get_settings

    get_settings.cache_clear()
    from api.main import app
    from api.routers import auth

    admins = {"admin@example.org": {"user_id": 7, "name": "Admin", "role": "admin", "block_id": None}}
    monkeypatch.setattr(auth, "_jwks_client", lambda url: _Jwks())
    monkeypatch.setattr(auth, "query_one", lambda sql, params: admins.get(params[0]))
    monkeypatch.setattr(auth, "execute", lambda sql, params: 1)
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def post(c, token=None):
    headers = {"Cf-Access-Jwt-Assertion": token} if token else {}
    return c.post("/auth/access", headers=headers)


def test_an_admin_email_gets_a_short_lived_admin_token(client):
    r = post(client, assertion())
    assert r.status_code == 200, r.text
    from common.config import get_settings

    claims = jwt.decode(r.json()["access_token"], get_settings().jwt_secret, algorithms=["HS256"])
    assert claims["sub"] == "7" and claims["role"] == "admin"
    assert claims["exp"] - time.time() <= 120 * 60 + 5


def test_the_email_is_matched_case_insensitively(client):
    assert post(client, assertion(email="Admin@Example.ORG")).status_code == 200


@pytest.mark.parametrize("token", [
    assertion(aud="b" * 64),
    assertion(iss="https://someone-else.cloudflareaccess.com"),
    assertion(exp_in=-60),
    assertion(key=OTHER),
    "not-a-jwt",
])
def test_an_unverifiable_assertion_is_refused(client, token):
    assert post(client, token).status_code == 401


def test_a_verified_email_that_is_not_an_admin_is_refused(client):
    assert post(client, assertion(email="someone@example.org")).status_code == 403


def test_no_assertion_is_refused(client):
    assert post(client).status_code == 401


def test_unconfigured_access_says_so(client, monkeypatch):
    monkeypatch.setenv("CF_ACCESS_AUD", "")
    from common.config import get_settings

    get_settings.cache_clear()
    assert post(client, assertion()).status_code == 503


def test_anonymous_visitors_are_the_public_viewer(client):
    me = client.get("/auth/me").json()
    assert me["role"] == "public" and me["sees_caste"] is False


def test_password_login_does_not_exist_in_production(monkeypatch):
    import importlib
    import sys

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", secrets.token_hex(32))
    from common.config import get_settings

    get_settings.cache_clear()
    saved = {n: m for n, m in sys.modules.items() if n == "api.main"}
    sys.modules.pop("api.main", None)
    try:
        main = importlib.import_module("api.main")
        with TestClient(main.app) as c:
            assert c.post("/auth/login", json={"username": "a", "password": "bbbbbbbb"}).status_code == 404
    finally:
        sys.modules.pop("api.main", None)
        sys.modules.update(saved)
        get_settings.cache_clear()
