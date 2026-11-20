from __future__ import annotations

import json
import logging
import socket
from pathlib import Path

from lapremote.banner import pairing_url, qr_ascii, render_banner
from lapremote.discovery import HOST_NAME, SERVICE_TYPE, build_service_info
from lapremote.logging_setup import BACKUP_COUNT, MAX_BYTES, get_logger, log_event, setup_logging


def test_pairing_url() -> None:
    assert pairing_url("192.168.1.20", 7777, "123456") == "http://192.168.1.20:7777/?pair=123456"
    assert (
        pairing_url("box.ts.net", 443, "000001", https=True)
        == "https://box.ts.net:443/?pair=000001"
    )


def test_qr_ascii_renders_blocks() -> None:
    art = qr_ascii("http://192.168.1.20:7777/?pair=123456")
    lines = art.splitlines()
    assert len(lines) > 10
    assert any(ch in art for ch in "█▀▄")


def test_banner_contains_url_and_code() -> None:
    text = render_banner("192.168.1.20", 7777, "654321", 5, https=False)
    assert "http://192.168.1.20:7777/?pair=654321" in text
    assert "Pairing code: 654321 (valid 5 min, single use)" in text
    assert chr(0x2014) not in text
    assert chr(0x2013) not in text


def test_banner_without_ip_explains_fix() -> None:
    text = render_banner(None, 7777, "654321", 5, https=False)
    assert "Connect to Wi-Fi" in text
    assert "654321" in text


def test_service_info() -> None:
    info = build_service_info("192.168.1.20", 7777, "MY-LAPTOP")
    assert info.type == SERVICE_TYPE
    assert info.server == HOST_NAME
    assert info.port == 7777
    assert info.addresses == [socket.inet_aton("192.168.1.20")]
    assert info.name == f"LapRemote on MY-LAPTOP.{SERVICE_TYPE}"


def test_service_info_sanitises_instance_name() -> None:
    info = build_service_info("10.0.0.2", 7777, "evil.name\x00._tcp")
    assert info.name == f"LapRemote on evilnametcp.{SERVICE_TYPE}"


def test_json_lines_log(tmp_path: Path) -> None:
    path = setup_logging(tmp_path / "logs", console=False)
    log_event(get_logger("test"), "hello", answer=42)
    for handler in logging.getLogger("lapremote").handlers:
        handler.flush()
    entry = json.loads(path.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert entry["event"] == "hello"
    assert entry["answer"] == 42
    assert entry["level"] == "info"
    assert entry["logger"] == "lapremote.test"


def test_rotation_settings(tmp_path: Path) -> None:
    setup_logging(tmp_path / "logs", console=False)
    handlers = [
        h for h in logging.getLogger("lapremote").handlers if isinstance(h, logging.FileHandler)
    ]
    assert len(handlers) == 1
    rotating = handlers[0]
    assert rotating.maxBytes == MAX_BYTES == 1_000_000  # type: ignore[attr-defined]
    assert rotating.backupCount == BACKUP_COUNT == 4  # type: ignore[attr-defined]


def test_setup_is_idempotent(tmp_path: Path) -> None:
    setup_logging(tmp_path / "a", console=True)
    setup_logging(tmp_path / "b", console=True)
    ours = [
        h
        for h in logging.getLogger("lapremote").handlers
        if getattr(h, "_lapremote_handler", False)
    ]
    assert len(ours) == 2
