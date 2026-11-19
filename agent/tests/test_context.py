from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lapremote.config import Config
from lapremote.core import Agent
from lapremote.system.context import (
    ContextService,
    ForegroundInfo,
    classify,
    make_reader,
    parse_xdotool,
    read_foreground,
)

from .wsclient import make_app, pair_new, phone


@pytest.mark.parametrize(
    ("process", "title", "app", "category", "site"),
    [
        # macOS app names
        ("Brave Browser", "Stranger Things | Netflix", "Brave", "browser", "netflix"),
        ("Google Chrome", "lofi - YouTube", "Chrome", "browser", "youtube"),
        ("Microsoft Edge", "Inbox", "Edge", "browser", "generic"),
        ("Safari", "Prime Video: Reacher", "Safari", "browser", "prime"),
        ("Microsoft PowerPoint", "Deck.pptx", "PowerPoint", "presentation", None),
        ("Keynote", "Talk", "Keynote", "presentation", None),
        ("Music", "", "Music", "music", None),
        ("QuickTime Player", "clip.mov", "QuickTime Player", "video", None),
        ("Finder", "", "Desktop", "desktop", None),
        # Linux process names
        ("brave", "YouTube - Brave", "Brave", "browser", "youtube"),
        ("soffice.bin", "slides.odp - LibreOffice Impress", "Impress", "presentation", None),
        ("rhythmbox", "Song", "Rhythmbox", "music", None),
        # Windows
        ("MusicBee.exe", "MusicBee", "MusicBee", "music", None),
        ("Notepad.exe", "notes.txt", "Notepad", "other", None),
    ],
)
def test_classify_across_platforms(
    process: str, title: str, app: str, category: str, site: str | None
) -> None:
    info = classify(process, title)
    assert (info.app, info.category, info.site) == (app, category, site)


def test_parse_xdotool() -> None:
    assert parse_xdotool("YouTube - Brave\n", "4242\n") == ("YouTube - Brave", 4242)
    assert parse_xdotool("x", "") is None


def test_reader_selection() -> None:
    assert make_reader("Windows") is not None
    assert make_reader("Darwin") is not None
    assert make_reader("Linux", "wayland") is None
    assert make_reader("Plan9") is None


@pytest.mark.skipif(sys.platform != "win32", reason="real foreground window is read on Windows")
def test_real_foreground_window_on_windows() -> None:
    info = read_foreground()
    # Something is always in front on a desktop session (the terminal or IDE running the tests).
    assert info is not None
    assert info.process_name
    assert info.category in ("browser", "music", "video", "presentation", "desktop", "other")


async def test_service_emits_only_on_change() -> None:
    agent = Agent(Config(), Path(sys.prefix) / "unused-home-never-written")
    sent: list[object] = []

    async def capture(type_: str, payload: object, where: object = None) -> None:
        sent.append(payload)

    agent.hub.broadcast = capture  # type: ignore[method-assign]
    frames = [
        classify("brave.exe", "Netflix - Brave"),
        classify("brave.exe", "Netflix - Brave"),
        classify("Spotify.exe", "Spotify"),
        None,
        classify("Spotify.exe", "Spotify"),
    ]
    queue = list(frames)
    service = ContextService(agent, lambda: queue.pop(0))
    for _ in frames:
        await service.poll_once()
    assert [getattr(p, "site", None) or getattr(p, "category", None) for p in sent] == [
        "netflix",
        "music",
    ]
    assert agent.feature_status["context"].available is False  # register() not called yet


async def test_failing_reader_is_survived() -> None:
    agent = Agent(Config(), Path(sys.prefix) / "unused-home-never-written")

    def broken() -> ForegroundInfo | None:
        raise OSError("window went away")

    service = ContextService(agent, broken)
    await service.poll_once()
    assert service.current is None


def test_context_state_pushed_on_connect(isolated_home: Path) -> None:
    info = classify("brave.exe", "Episode 1 | Netflix - Brave")
    app = make_app(isolated_home, foreground_reader=lambda: info)
    with TestClient(app) as client:
        device_id, token, _ = pair_new(client, app)
        with phone(client) as p:
            ok = p.resume(device_id, token)
            assert ok["payload"]["features"]["context"]["available"] is True
            state = p.recv_type("context.state")["payload"]
    assert state["app"] == "Brave"
    assert state["category"] == "browser"
    assert state["site"] == "netflix"
    assert state["processName"] == "brave.exe"
    assert state["ts"] > 0


def test_context_unavailable_without_reader(isolated_home: Path) -> None:
    app = make_app(isolated_home)
    with TestClient(app) as client:
        code = app.state.agent.pairing.current()[0]
        with phone(client) as p:
            features = p.pair(code)["payload"]["features"]
    assert features["context"] == {
        "available": False,
        "reason": "This laptop can't tell which app is in front.",
    }
