from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lapremote import __version__
from lapremote.server import origin_allowed

from .wsclient import make_app


def test_health_returns_only_ok_version_uptime(isolated_home: Path) -> None:
    with TestClient(make_app(isolated_home)) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"ok", "version", "uptime"}
    assert body["ok"] is True
    assert body["version"] == __version__
    assert body["uptime"] >= 0


def test_api_docs_are_disabled(isolated_home: Path) -> None:
    with TestClient(make_app(isolated_home)) as client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert client.get(path).status_code == 404


def test_health_rejects_post(isolated_home: Path) -> None:
    with TestClient(make_app(isolated_home)) as client:
        assert client.post("/api/health").status_code == 405


def test_not_built_page_when_static_missing(isolated_home: Path) -> None:
    with TestClient(make_app(isolated_home)) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "hasn't been built yet" in response.text


@pytest.fixture
def static_dir(tmp_path: Path) -> Path:
    root = tmp_path / "static"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<!doctype html><title>LapRemote</title>", encoding="utf-8")
    (root / "assets" / "app-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("nope", encoding="utf-8")
    return root


def test_static_app_is_served_with_spa_fallback(isolated_home: Path, static_dir: Path) -> None:
    with TestClient(make_app(isolated_home, static_dir=static_dir)) as client:
        index = client.get("/?pair=123456")
        assert index.status_code == 200
        assert "LapRemote" in index.text
        assert index.headers["cache-control"] == "no-cache"
        asset = client.get("/assets/app-abc123.js")
        assert asset.status_code == 200
        assert "immutable" in asset.headers["cache-control"]
        deep = client.get("/settings/devices")
        assert deep.status_code == 200
        assert "LapRemote" in deep.text
        assert client.get("/api/health").json()["ok"] is True
        assert client.get("/api/unknown").status_code == 404


def test_static_blocks_path_traversal(isolated_home: Path, static_dir: Path) -> None:
    with TestClient(make_app(isolated_home, static_dir=static_dir)) as client:
        for path in ("/../secret.txt", "/assets/../../secret.txt", "/%2e%2e/secret.txt"):
            response = client.get(path)
            assert "nope" not in response.text


@pytest.mark.parametrize(
    ("origin", "host", "allowed"),
    [
        ("http://192.168.1.20:7777", "192.168.1.20:7777", True),
        ("http://LAPREMOTE.local:7777", "lapremote.local:7777", True),
        ("https://box.tailnet.ts.net", "box.tailnet.ts.net", True),
        ("https://box.tailnet.ts.net", "box.tailnet.ts.net:443", True),
        ("http://localhost:5173", "localhost:5173", True),
        ("http://evil.example", "192.168.1.20:7777", False),
        ("http://192.168.1.20:7778", "192.168.1.20:7777", False),
        ("file://", "192.168.1.20:7777", False),
        (None, "192.168.1.20:7777", False),
        ("http://192.168.1.20:7777", None, False),
    ],
)
def test_origin_allowed(origin: str | None, host: str | None, allowed: bool) -> None:
    assert origin_allowed(origin, host) is allowed
