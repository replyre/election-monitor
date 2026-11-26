"""Production refuses the stub adapter, hides the route map and the unused webhook,
and never serves stored media as anything a browser would execute."""

from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from pulse.api.main import create_app
from pulse.api.media_response import media_response
from pulse.config import ConfigError, check_settings


def test_production_refuses_the_stub_adapter(settings):
    with pytest.raises(ConfigError, match="CORE_ADAPTER must be core in production"):
        check_settings(replace(settings, production=True))


def test_production_refuses_demo_mode(settings):
    with pytest.raises(ConfigError, match="DEMO_MODE cannot run in production"):
        check_settings(replace(settings, production=True, demo_mode=True, core_adapter="core",
                               core_database_url="postgresql://x/y", core_jwt_secret="c" * 40))


@pytest.mark.parametrize("production, visible", [(False, 200), (True, 404)])
def test_the_route_map_is_hidden_in_production(settings, pool, core, fake_tg, production, visible):
    app = create_app(replace(settings, production=production), pool=pool, core=core,
                     telegram_client=fake_tg)
    with TestClient(app) as c:
        for path in ("/docs", "/openapi.json"):
            assert c.get(path).status_code == visible


@pytest.mark.parametrize("production, mode, mounted", [
    (False, "polling", True), (True, "polling", False), (True, "webhook", True)])
def test_the_webhook_route_exists_only_when_it_can_be_used(settings, pool, core, fake_tg,
                                                          production, mode, mounted):
    s = replace(settings, production=production, bot_mode=mode,
                webhook_url="https://example.invalid/telegram/webhook" if mode == "webhook" else None)
    app = create_app(s, pool=pool, core=core, telegram_client=fake_tg)
    with TestClient(app) as c:
        status = c.post("/telegram/webhook", json={}).status_code
    assert (status != 404) is mounted


@pytest.mark.parametrize("mime", ["text/html", "image/svg+xml", "application/javascript",
                                  "text/html; charset=utf-8", "", None, "IMAGE/SVG+XML"])
def test_media_that_could_run_script_downloads_as_an_opaque_file(mime):
    r = media_response(b"<script>alert(1)</script>", mime)
    assert r.media_type == "application/octet-stream"
    assert r.headers["content-disposition"] == "attachment"
    assert "sandbox" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("mime", ["image/jpeg", "audio/ogg", "video/mp4", "Audio/OGG; codecs=opus"])
def test_real_media_is_served_inline_and_sandboxed(mime):
    r = media_response(b"\x00", mime)
    assert r.media_type == mime.split(";")[0].lower()
    assert r.headers["content-disposition"] == "inline"
    assert "sandbox" in r.headers["content-security-policy"]
