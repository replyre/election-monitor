"""Directory API routes."""

from __future__ import annotations

from api.routers import directory


def test_directory_router_registered():
    paths = [getattr(r, "path", "") for r in directory.router.routes]
    prefix = "/acs/{ac_number}/directory"
    assert f"{prefix}/panchayats" in paths
    assert f"{prefix}/polling-stations" in paths
    assert f"{prefix}/officials" in paths
    assert f"{prefix}/poll-calendar" in paths
    assert f"{prefix}/panchayats/{{area_id}}/villages" in paths
