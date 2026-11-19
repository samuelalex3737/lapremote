from __future__ import annotations

import sys

from fastapi.testclient import TestClient

from lapremote import __version__
from lapremote.server import create_app
from lapremote.system.platform_info import detect_os


def test_health_reports_version_and_os() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "app": "lapremote",
        "version": __version__,
        "os": detect_os(sys.platform),
    }


def test_api_docs_are_disabled() -> None:
    with TestClient(create_app()) as client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert client.get(path).status_code == 404


def test_unknown_route_is_404() -> None:
    with TestClient(create_app()) as client:
        assert client.get("/api/nope").status_code == 404


def test_health_rejects_post() -> None:
    with TestClient(create_app()) as client:
        assert client.post("/api/health").status_code == 405
