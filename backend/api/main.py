"""FastAPI application (LLD 9).

    uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 2
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routers import acs, admin, admins, auth, data, directory, legacy, news, scenario
from common.config import get_settings
from common.db import close_pools, get_pool, query, query_one
from common.logging_setup import get_logger, setup_logging
from common.secrets import check_jwt_secret

log = get_logger(__name__)

# Stamped at import. The frontend reads it from /config so a stale cached bundle
# is identifiable: if the version chip does not move after a deploy, the browser
# is still running the old build.
BUILD_TIME = datetime.now(UTC).isoformat(timespec="seconds")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    settings = get_settings()

    # E1: refuse to start rather than log and carry on. The previous code logged
    # "every authenticated request will fail", which was wrong in the dangerous
    # direction - HS256 verification with an empty key succeeds, so an unset
    # secret was an unauthenticated admin login, not a broken one. Raising here
    # means uvicorn exits; the module still imports, so the app stays
    # introspectable.
    check_jwt_secret(settings.jwt_secret)
    # Admin accounts are bootstrapped by `python -m scripts.ensure_admins` at
    # deploy time, not here: startup must not depend on Postgres being up.

    # Open the pool now so the first request does not pay the TLS handshake to
    # the database. Non-blocking: connections are made in the background.
    if settings.database_url:
        try:
            get_pool()
        except Exception as exc:
            log.warning("could not open the database pool at startup (%s)", type(exc).__name__)

    log.info("starting API (env=%s)", settings.app_env)
    yield
    close_pools()


app = FastAPI(
    title="Giridih AC-32 Election Monitor",
    description=(
        "Booth-level election analytics for the Giridih assembly constituency, Jharkhand. "
        "Holds no individual voter records: electoral rolls are parsed into per-booth counts "
        "and the names discarded. Community figures are estimates and carry a confidence score. "
        "Review every figure before relying on it."
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None if get_settings().is_production else "/docs",
    redoc_url=None if get_settings().is_production else "/redoc",
    openapi_url=None if get_settings().is_production else "/openapi.json",
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins or ["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def cache_policy(request: Request, call_next):
    """Authenticated data may sit in the viewer's own browser for a minute (it
    changes only when the jobs refresh the views) but never in a shared cache;
    auth and admin responses are not stored at all."""
    response = await call_next(request)
    if "cache-control" not in response.headers:
        path = request.url.path
        if path.startswith("/auth") or "/admin" in path or request.method != "GET":
            response.headers["Cache-Control"] = "no-store"
        elif response.status_code == 200 and path.startswith("/acs/"):
            response.headers["Cache-Control"] = "private, max-age=60"
        else:
            response.headers["Cache-Control"] = "no-cache"
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception) -> JSONResponse:
    """Never leak an internal error to the client; log it in full instead."""
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal error. This has been logged."},
    )


@app.get("/health", tags=["ops"])
def health(response: Response) -> dict:
    """Liveness plus a database probe.

    Returns 503 when the database is unreachable, not 200. It used to return 200
    either way with a "degraded" string in the body, which meant the compose
    healthcheck - and any load balancer or uptime monitor doing the ordinary
    thing of looking at the status code - reported the service healthy while
    every data route was timing out. An API that cannot reach the database
    cannot serve a single page, so it is not healthy.
    """
    try:
        query_one("SELECT 1 AS ok")
        db_ok = True
        detail = None
    except Exception as exc:
        log.warning("health check: database unreachable (%s)", exc)
        db_ok = False
        # The class name, not the message: a psycopg error can carry the host,
        # the database name and the user, and /health is unauthenticated.
        detail = type(exc).__name__

    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if db_ok else "unavailable",
        "database": db_ok,
        "error": detail,
    }


@app.get("/config", tags=["ops"])
def config() -> dict:
    """Boot-time configuration the frontend needs before it has a token.

    Deliberately unauthenticated and deliberately small. It exposes feature
    flags and build metadata only - no connection strings, no key material, no
    model names.
    """
    # The constituency list is here as well as at /acs because the frontend
    # needs it before it has a token: the AC switcher sits in the header, which
    # renders on the login screen. Identity and the verified flag only, never a
    # figure.
    try:
        acs_list = query(
            "SELECT ac_number, name_en, name_hi, reservation, verified, "
            "EXISTS (SELECT 1 FROM booth b WHERE b.ac_id = ac.ac_id) AS has_booths "
            "FROM ac WHERE is_active ORDER BY ac_number"
        )
    except Exception as exc:
        # /config has to answer even with the database down, or the frontend
        # cannot boot far enough to show why it is broken.
        log.warning("/config could not list constituencies (%s)", type(exc).__name__)
        acs_list = []
    return {
        "acs": acs_list,
        # The first AC with booths loaded, else the first listed. It used to be
        # the first by number - 31, Gandey, which has no booth data - so a
        # first-time visitor landed on an empty dashboard.
        # Now that every AC has booth results, the verified one (Giridih, the
        # by-election seat) comes first.
        "default_ac": next((a["ac_number"] for a in acs_list if a["has_booths"] and a["verified"]),
                           next((a["ac_number"] for a in acs_list if a["has_booths"]),
                                acs_list[0]["ac_number"] if acs_list else None)),
        "version": app.version,
        "build_time": BUILD_TIME,
        "admin_url": get_settings().admin_url or None,
    }


app.include_router(auth.router)
app.include_router(admins.router)
# Password sign-in is for local development and the test suites; production
# admins sign in through Cloudflare Access (POST /auth/access).
if not settings.is_production:
    app.include_router(auth.password_router)
app.include_router(acs.router)
app.include_router(data.router)
app.include_router(directory.router)
app.include_router(news.router)
app.include_router(scenario.router)
app.include_router(admin.router)

# Registered last so the scoped routes above always win a path match. These are
# 308 redirects from the pre-multi-AC paths and come out one release later.
app.include_router(legacy.router)
