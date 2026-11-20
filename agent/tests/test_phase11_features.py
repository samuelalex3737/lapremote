"""Features after v1.0.0: installed apps and Store apps, shortcut icons, clipboard and links,
file upload, layouts, other laptops on the network and Wake-on-LAN."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from lapremote.apps import store_app_id
from lapremote.config import Config
from lapremote.core import Agent
from lapremote.layouts import default_layouts
from lapremote.peers import PeerService, magic_packet, normalise_mac, sighting_from
from lapremote.protocol import AppInfo
from lapremote.site_icons import (
    BlockedHostError,
    check_public,
    decode_icon,
    fetch_site_icon,
    icon_links,
)
from lapremote.upload import clean_name, free_path

from .fakes import FakeApps, FakeClipboard, FakeLauncher
from .wsclient import ORIGIN, Phone, agent_of, make_app, pair_new, phone

WINDOWS_ONLY = pytest.mark.skipif(sys.platform != "win32", reason="Windows app ids")


def png_bytes(size: int = 64, color: tuple[int, int, int] = (200, 30, 30)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (size, size), color).save(out, format="PNG")
    return out.getvalue()


def owner_and_guest(client: TestClient, app: Any) -> tuple[tuple[str, str], tuple[str, str]]:
    owner = pair_new(client, app, "Owner")
    guest = pair_new(client, app, "Guest")
    return (owner[0], owner[1]), (guest[0], guest[1])


# ---------------------------------------------------------------- installed apps


def test_store_exe_path_becomes_the_app_id(tmp_path: Path) -> None:
    package = tmp_path / "WindowsApps" / "SpotifyAB.SpotifyMusic_1.310.2586.0_x64__zpdnekdrzrea0"
    package.mkdir(parents=True)
    (package / "AppxManifest.xml").write_text(
        '<Applications><Application Id="Spotify" Executable="SpotifyMigrator.exe" />'
        '<Application Id="SpotifyLauncher" Executable="SpotifyLauncher.exe" /></Applications>',
        encoding="utf-8",
    )
    installed = [
        AppInfo(app_id="SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify", name="Spotify"),
        AppInfo(app_id="SpotifyAB.SpotifyMusic_zpdnekdrzrea0!SpotifyLauncher", name="Launcher"),
    ]
    # Spotify.exe has no entry of its own: the package's Start-menu app is used.
    assert store_app_id(str(package / "Spotify.exe"), installed) == installed[0].app_id
    # An exe that is an app entry maps to exactly that app.
    assert store_app_id(str(package / "SpotifyLauncher.exe"), installed) == installed[1].app_id
    # Not installed, or not a Store path: nothing.
    assert store_app_id(str(package / "Spotify.exe"), []) is None
    assert store_app_id(r"C:\Program Files\VLC\vlc.exe", installed) is None


def save(p: Phone, shortcut: dict[str, Any]) -> dict[str, Any]:
    return p.ack_for(p.send("shortcuts.save", {"shortcut": shortcut}))


@WINDOWS_ONLY
def test_app_shortcuts_by_installed_id_and_store_path(isolated_home: Path, tmp_path: Path) -> None:
    launcher = FakeLauncher()
    apps = FakeApps()
    app = make_app(isolated_home, launcher=launcher, app_source=apps)
    with TestClient(app) as client:
        device_id, token, _ = pair_new(client, app)
        with phone(client) as p:
            p.resume(device_id, token)
            ok = save(
                p,
                {"id": "spotify-app", "name": "Spotify", "kind": "app", "app": apps.apps[0].app_id},
            )
            assert ok["ok"] is True
            missing = save(
                p, {"id": "nope", "name": "Nope", "kind": "app", "app": "Not.Installed!App"}
            )
            assert missing["error"] == "That app isn't installed on this laptop."
            assert p.ack_for(p.send("launch.open", {"shortcutId": "spotify-app"}))["ok"] is True
            p.send("apps.list", {})
            state = p.recv_type("apps.state", limit=40)["payload"]
    assert launcher.apps == [apps.apps[0].app_id]
    assert [a["appId"] for a in state["apps"]] == [a.app_id for a in apps.apps]


@WINDOWS_ONLY
def test_old_store_path_is_upgraded_when_launched(isolated_home: Path, tmp_path: Path) -> None:
    # The real failure: a Spotify.exe path from WindowsApps, which Windows refuses to start.
    package = tmp_path / "WindowsApps" / "SpotifyAB.SpotifyMusic_1.310.2586.0_x64__zpdnekdrzrea0"
    package.mkdir(parents=True)
    exe = package / "Spotify.exe"
    exe.write_bytes(b"MZ")
    isolated_home.mkdir(parents=True, exist_ok=True)
    (isolated_home / "shortcuts.json").write_text(
        json.dumps([{"id": "spotify-2", "name": "Spotify", "kind": "app", "app": str(exe)}]),
        encoding="utf-8",
    )
    launcher = FakeLauncher()
    app = make_app(isolated_home, launcher=launcher)
    with TestClient(app) as client:
        device_id, token, _ = pair_new(client, app)
        with phone(client) as p:
            p.resume(device_id, token)
            assert p.ack_for(p.send("launch.open", {"shortcutId": "spotify-2"}), limit=40)["ok"]
    assert launcher.apps == ["SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify"]
    stored = json.loads((isolated_home / "shortcuts.json").read_text(encoding="utf-8"))
    assert stored[0]["app"] == "SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify"


def test_guests_cannot_list_apps(isolated_home: Path) -> None:
    app = make_app(isolated_home)
    with TestClient(app) as client:
        _owner, (guest_id, guest_token) = owner_and_guest(client, app)
        with phone(client) as p:
            p.resume(guest_id, guest_token)
            assert p.ack_for(p.send("apps.list", {}))["error"] == "Only the owner can do that."


# ---------------------------------------------------------------- shortcut icons


def wait_for_image(p: Phone, shortcut_id: str) -> str:
    for _ in range(40):
        message = p.recv()
        if message["type"] != "shortcuts.state":
            continue
        for s in message["payload"]["shortcuts"]:
            if s["id"] == shortcut_id and s.get("image"):
                return str(s["image"])
    msg = "no image arrived"
    raise AssertionError(msg)


def test_site_icon_is_made_by_the_laptop_and_never_taken_from_the_phone(
    isolated_home: Path,
) -> None:
    fetched: list[str] = []

    async def fake_site_icon(url: str) -> str | None:
        fetched.append(url)
        return "data:image/png;base64,SITE"

    app = make_app(isolated_home, site_icon=fake_site_icon)
    with TestClient(app) as client:
        device_id, token, _ = pair_new(client, app)
        with phone(client) as p:
            p.resume(device_id, token)
            sneaky = {
                "id": "twitch",
                "name": "Twitch",
                "kind": "url",
                "url": "https://twitch.tv/",
                "image": "data:image/png;base64,FROM-THE-PHONE",
            }
            assert save(p, sneaky)["ok"] is True
            assert wait_for_image(p, "twitch") == "data:image/png;base64,SITE"
            # Saving again with the same address keeps the image and fetches nothing new.
            assert save(p, {**sneaky, "name": "Twitch TV"})["ok"] is True
    assert fetched == ["https://twitch.tv/"]
    stored = json.loads((isolated_home / "shortcuts.json").read_text(encoding="utf-8"))
    assert next(s for s in stored if s["id"] == "twitch")["image"] == "data:image/png;base64,SITE"


def test_built_in_icons_are_left_alone(isolated_home: Path) -> None:
    calls: list[str] = []

    async def fake_site_icon(url: str) -> str | None:
        calls.append(url)
        return "data:image/png;base64,X"

    app = make_app(isolated_home, site_icon=fake_site_icon)
    with TestClient(app):
        time.sleep(0.3)
    # The default shortcuts (Netflix, YouTube...) have built-in icons, so nothing is fetched.
    assert calls == []


# ---------------------------------------------------------------- site icon safety


async def public(_host: str) -> list[str]:
    return ["93.184.216.34"]


def test_private_and_loopback_hosts_are_refused() -> None:
    async def resolve(host: str) -> list[str]:
        return {"router.lan": ["192.168.1.1"], "me": ["127.0.0.1"], "v6": ["::1"]}[host]

    for url in ("http://router.lan/", "http://me:7777/", "http://v6/"):
        with pytest.raises(BlockedHostError):
            asyncio.run(check_public(url, resolve))
    with pytest.raises(BlockedHostError):
        asyncio.run(check_public("ftp://example.org/", public))
    asyncio.run(check_public("https://example.org/", public))


def test_icon_links_prefer_apple_touch_and_skip_svg() -> None:
    html = """
      <link rel="icon" href="/fav-16.png" sizes="16x16">
      <link rel="icon" type="image/svg+xml" href="/logo.svg">
      <link rel='apple-touch-icon' href='/apple.png'>
      <link rel="icon" href="https://cdn.example.org/big.png" sizes="64x64">
    """
    assert icon_links("https://example.org/page", html) == [
        "https://example.org/apple.png",
        "https://cdn.example.org/big.png",
        "https://example.org/fav-16.png",
        "https://example.org/favicon.ico",
    ]


def test_decode_icon_reencodes_and_rejects_junk() -> None:
    icon = decode_icon(png_bytes(128))
    assert icon is not None
    raw = base64.b64decode(icon.split(",", 1)[1])
    with Image.open(io.BytesIO(raw)) as image:
        assert image.size == (96, 96)
        assert image.format == "PNG"
    assert decode_icon(b"<html>not an image</html>") is None
    assert decode_icon(png_bytes(4)) is None  # too small to be an icon


def test_fetch_site_icon_end_to_end_with_a_redirect_into_the_lan_blocked() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(
                200, headers={"content-type": "text/html"}, text='<link rel="icon" href="/i.png">'
            )
        if request.url.path == "/i.png":
            return httpx.Response(200, content=png_bytes(32))
        if request.url.path == "/sneaky":
            return httpx.Response(302, headers={"location": "http://router.lan/admin.png"})
        return httpx.Response(404)

    async def resolve(host: str) -> list[str]:
        return ["192.168.1.1"] if host == "router.lan" else ["93.184.216.34"]

    async def go(url: str) -> str | None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_site_icon(url, client, resolve)

    assert (asyncio.run(go("https://example.org/")) or "").startswith("data:image/png;base64,")
    assert asyncio.run(go("https://example.org/sneaky")) is None


def test_fetch_site_icon_caps_the_size() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "text/html"}, content=b"x" * (600 * 1024)
        )

    async def go() -> str | None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_site_icon("https://example.org/", client, public)

    assert asyncio.run(go()) is None


# ---------------------------------------------------------------- clipboard and links


def test_clipboard_both_ways_and_links(isolated_home: Path) -> None:
    clipboard = FakeClipboard("from the laptop")
    launcher = FakeLauncher()
    app = make_app(isolated_home, clipboard=clipboard, launcher=launcher)
    with TestClient(app) as client:
        device_id, token, _ = pair_new(client, app)
        with phone(client) as p:
            p.resume(device_id, token)
            assert p.ack_for(p.send("clipboard.set", {"text": "hello laptop"}))["ok"] is True
            p.send("clipboard.get", {})
            got = p.recv_type("clipboard.state", limit=40)["payload"]
            assert got["text"] == "hello laptop"
            assert p.ack_for(p.send("url.open", {"url": "https://example.org/a"}))["ok"] is True
            bad = p.ack_for(p.send("url.open", {"url": "file:///C:/Windows/system32/calc.exe"}))
            assert bad["ok"] is False
            clipboard.busy = True
            busy = p.ack_for(p.send("clipboard.set", {"text": "x"}))
            assert busy["error"] == "Couldn't use the laptop's clipboard. Try again."
            clipboard.busy = False
            clipboard.text = "sent from the tray"
            sent = client.portal.call(app.state.services.clipboard.send_to_phones)  # type: ignore[union-attr]
            assert sent == 1
            assert (
                p.recv_type("clipboard.state", limit=40)["payload"]["text"] == "sent from the tray"
            )
    assert launcher.urls == ["https://example.org/a"]
    # Clipboard text is never written to the log.
    log_text = (isolated_home / "logs" / "agent.log").read_text(encoding="utf-8")
    assert "hello laptop" not in log_text
    assert "sent from the tray" not in log_text


def test_guests_cannot_touch_the_clipboard(isolated_home: Path) -> None:
    clipboard = FakeClipboard("secret")
    app = make_app(isolated_home, clipboard=clipboard)
    with TestClient(app) as client:
        _owner, (guest_id, guest_token) = owner_and_guest(client, app)
        with phone(client) as p:
            p.resume(guest_id, guest_token)
            for message, payload in (
                ("clipboard.get", {}),
                ("clipboard.set", {"text": "x"}),
                ("url.open", {"url": "https://example.org/"}),
            ):
                assert p.ack_for(p.send(message, payload))["error"] == "Only the owner can do that."
    assert clipboard.text == "secret"


def test_clipboard_text_limit(isolated_home: Path) -> None:
    app = make_app(isolated_home)
    with TestClient(app) as client:
        device_id, token, _ = pair_new(client, app)
        with phone(client) as p:
            p.resume(device_id, token)
            too_long = p.ack_for(p.send("clipboard.set", {"text": "x" * 100_001}))
            assert too_long["ok"] is False


# ---------------------------------------------------------------- file upload


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("photo.jpg", "photo.jpg"),
        ("..%2F..%2Fetc%2Fpasswd", "passwd"),
        (r"C:\Users\x\Desktop\evil.exe", "evil.exe"),
        ("CON.txt", "_CON.txt"),
        ("nul", "_nul"),
        ("a<b>c:d?.png", "a_b_c_d_.png"),
        ("  .hidden  ", "hidden"),
        ("", "file"),
        ("line\nbreak.txt", "line_break.txt"),
        ("x" * 300 + ".jpeg", "x" * 115 + ".jpeg"),  # exactly the 120-character limit
    ],
)
def test_upload_names_are_cleaned(raw: str, clean: str) -> None:
    assert clean_name(raw) == clean


def test_uploads_never_overwrite(tmp_path: Path) -> None:
    (tmp_path / "a.jpg").write_bytes(b"1")
    (tmp_path / "a (2).jpg").write_bytes(b"2")
    assert free_path(tmp_path, "a.jpg").name == "a (3).jpg"
    assert free_path(tmp_path, "b").name == "b"


def upload(
    client: TestClient, device: tuple[str, str], body: bytes, name: str, **headers: str
) -> httpx.Response:
    base = {
        "X-LapRemote-Device": device[0],
        "Authorization": f"Bearer {device[1]}",
        "X-LapRemote-Filename": name,
        "Origin": ORIGIN,
    }
    response: httpx.Response = client.post("/api/upload", content=body, headers={**base, **headers})
    return response


def test_upload_saves_to_the_folder_with_safe_names(isolated_home: Path, tmp_path: Path) -> None:
    folder = tmp_path / "Downloads" / "LapRemote"
    app = make_app(isolated_home, upload_folder=folder)
    with TestClient(app) as client:
        owner, guest = owner_and_guest(client, app)
        photo = png_bytes(32)
        ok = upload(client, owner, photo, "holiday%20photo.png")
        assert ok.json() == {"ok": True, "name": "holiday photo.png", "size": len(photo)}
        again = upload(client, owner, photo, "holiday%20photo.png")
        assert again.json()["name"] == "holiday photo (2).png"
        sneaky = upload(client, owner, b"x", "..%2F..%2Foutside.txt")
        assert sneaky.json()["name"] == "outside.txt"
        assert upload(client, guest, photo, "g.png").status_code == 403
        assert upload(client, (owner[0], "wrong-token"), photo, "w.png").status_code == 401
        assert (
            upload(client, owner, photo, "o.png", Origin="https://evil.example").status_code == 403
        )
        too_big = upload(
            client, owner, b"x", "big.bin", **{"Content-Length": str(101 * 1024 * 1024)}
        )
        assert too_big.status_code == 413
        assert upload(client, owner, b"", "empty.txt").status_code == 400
    names = sorted(p.name for p in folder.iterdir())
    assert names == ["holiday photo (2).png", "holiday photo.png", "outside.txt"]
    assert not (tmp_path / "outside.txt").exists()
    if sys.platform == "win32":
        zone = Path(f"{folder / 'holiday photo.png'}:Zone.Identifier").read_text(encoding="ascii")
        assert "ZoneId=3" in zone


# ---------------------------------------------------------------- layouts


def test_default_layouts_include_call_controls_for_each_os() -> None:
    windows = {layout.id: layout for layout in default_layouts("windows")}
    mac = {layout.id: layout for layout in default_layouts("macos")}
    assert {"zoom", "teams", "meet", "vlc", "spotify", "youtube"} <= set(windows)
    zoom_mute = windows["zoom"].buttons[0].action.model_dump()
    assert zoom_mute == {"type": "key", "key": "a", "modifiers": ["alt"]}
    assert mac["zoom"].buttons[0].action.model_dump()["modifiers"] == ["meta", "shift"]
    teams_mute = windows["teams"].buttons[0].action.model_dump()
    assert teams_mute == {"type": "key", "key": "m", "modifiers": ["ctrl", "shift"]}
    assert mac["meet"].buttons[0].action.model_dump()["modifiers"] == ["meta"]
    assert windows["meet"].match.titles == ["Meet - ", "Google Meet"]


def layout_payload(**over: Any) -> dict[str, Any]:
    base = {
        "id": "game",
        "name": "My game",
        "match": {"processes": ["  Game.EXE "], "titles": [" Level "]},
        "buttons": [{"label": "Jump", "action": {"type": "key", "key": "space"}}],
    }
    return {**base, **over}


def test_layouts_save_delete_and_push(isolated_home: Path) -> None:
    app = make_app(isolated_home)
    with TestClient(app) as client:
        (owner_id, owner_token), (guest_id, guest_token) = owner_and_guest(client, app)
        with phone(client) as p:
            p.resume(owner_id, owner_token)
            first = p.recv_type("layouts.state", limit=40)["payload"]["layouts"]
            assert any(layout["id"] == "zoom" for layout in first)
            # The new list is pushed just before the ack, so keep what came first.
            ack, before = p.ack_with(p.send("layouts.save", {"layout": layout_payload()}))
            assert ack["ok"] is True
            pushed = next(m for m in before if m["type"] == "layouts.state")
            saved = next(x for x in pushed["payload"]["layouts"] if x["id"] == "game")
            # Matching is normalised: process names trimmed and lowercased, titles trimmed.
            assert saved["match"]["processes"] == ["game.exe"]
            assert saved["match"]["titles"] == ["Level"]
            bad = p.ack_for(
                p.send(
                    "layouts.save",
                    {
                        "layout": layout_payload(
                            buttons=[{"label": "X", "action": {"type": "shell", "cmd": "calc"}}]
                        )
                    },
                )
            )
            assert bad["ok"] is False
            bad_key = p.ack_for(
                p.send(
                    "layouts.save",
                    {
                        "layout": layout_payload(
                            buttons=[{"label": "X", "action": {"type": "key", "key": "rm -rf"}}]
                        )
                    },
                )
            )
            assert bad_key["ok"] is False
            assert p.ack_for(p.send("layouts.delete", {"layoutId": "game"}))["ok"] is True
            gone = p.ack_for(p.send("layouts.delete", {"layoutId": "game"}))
            assert gone["error"] == "That layout doesn't exist anymore."
        with phone(client) as g:
            g.resume(guest_id, guest_token)
            denied = g.ack_for(g.send("layouts.save", {"layout": layout_payload()}))
            assert denied["error"] == "Only the owner can do that."
    stored = json.loads((isolated_home / "layouts.json").read_text(encoding="utf-8"))
    assert all(layout["id"] != "game" for layout in stored)


def test_broken_layouts_file_falls_back_to_defaults(isolated_home: Path) -> None:
    isolated_home.mkdir(parents=True, exist_ok=True)
    (isolated_home / "layouts.json").write_text("{oops", encoding="utf-8")
    app = make_app(isolated_home)
    with TestClient(app):
        pass
    assert (isolated_home / "layouts.json.broken").read_text(encoding="utf-8") == "{oops"
    assert json.loads((isolated_home / "layouts.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- other laptops and wake


PEER_ID = "0123456789abcdef"


def txt(**fields: str) -> dict[bytes, bytes | None]:
    return {k.encode(): v.encode() for k, v in fields.items()}


def test_sightings_are_checked() -> None:
    good = sighting_from(
        txt(id=PEER_ID, name="Den PC", mac="aa-bb-cc-dd-ee-ff", https="1"), "192.168.1.40", 7777
    )
    assert good is not None
    assert good.url == "https://192.168.1.40:7777/"
    assert good.mac == "AA:BB:CC:DD:EE:FF"
    assert sighting_from(txt(id="short", name="x"), "192.168.1.40", 7777) is None
    # Only laptops on the local network: never a public address.
    assert sighting_from(txt(id=PEER_ID), "8.8.8.8", 7777) is None
    assert sighting_from(txt(id=PEER_ID), "not-an-ip", 7777) is None
    weird = sighting_from(txt(id=PEER_ID, name="\x1b[31mEvil\n"), "10.0.0.5", 80)
    assert weird is not None
    assert weird.name == "[31mEvil"


def test_mac_and_magic_packet() -> None:
    assert normalise_mac("aa:bb:cc:dd:ee:ff") == "AA:BB:CC:DD:EE:FF"
    assert normalise_mac("00-00-00-00-00-00") is None
    assert normalise_mac("12:34") is None
    packet = magic_packet("AA:BB:CC:DD:EE:FF")
    assert len(packet) == 102
    assert packet[:6] == b"\xff" * 6
    assert packet[6:] == bytes.fromhex("AABBCCDDEEFF") * 16


def test_peers_are_listed_remembered_and_woken(isolated_home: Path) -> None:
    sent: list[tuple[str, list[str]]] = []
    app = make_app(isolated_home, wol_sender=lambda mac, targets: sent.append((mac, targets)))
    peers: PeerService = app.state.services.peers
    sighting = sighting_from(
        txt(id=PEER_ID, name="Den PC", mac="AA:BB:CC:DD:EE:FF"), "192.168.1.40", 7777
    )
    own = sighting_from(txt(id=peers.own_id, name="Me"), "192.168.1.33", 7777)
    assert sighting is not None
    assert own is not None
    with TestClient(app) as client:
        (owner_id, owner_token), (guest_id, guest_token) = owner_and_guest(client, app)
        with phone(client) as p:
            p.resume(owner_id, owner_token)
            assert p.recv_type("peers.state", limit=40)["payload"] == {"peers": []}
            client.portal.call(peers.seen, own)  # type: ignore[union-attr]
            client.portal.call(peers.seen, sighting)  # type: ignore[union-attr]
            listed = p.recv_type("peers.state", limit=40)["payload"]["peers"]
            assert [(x["name"], x["online"], x["mac"]) for x in listed] == [
                ("Den PC", True, "AA:BB:CC:DD:EE:FF")
            ]
            client.portal.call(peers.gone, PEER_ID)  # type: ignore[union-attr]
            asleep = p.recv_type("peers.state", limit=40)["payload"]["peers"]
            assert asleep[0]["online"] is False
            assert p.ack_for(p.send("wol.wake", {"mac": "AA:BB:CC:DD:EE:FF"}))["ok"] is True
            unknown = p.ack_for(p.send("wol.wake", {"mac": "11:22:33:44:55:66"}))
            assert unknown["error"] == "That laptop isn't one this laptop has seen."
            bad = p.ack_for(p.send("wol.wake", {"mac": "aa:bb:cc:dd:ee:ff"}))
            assert bad["ok"] is False  # lower case isn't the wire format
        with phone(client) as g:
            g.resume(guest_id, guest_token)
            assert (
                g.ack_for(g.send("wol.wake", {"mac": "AA:BB:CC:DD:EE:FF"}))["error"]
                == "Only the owner can do that."
            )
    assert sent[0][0] == "AA:BB:CC:DD:EE:FF"
    assert "255.255.255.255" in sent[0][1]
    assert len(sent) == 1
    # Remembered across restarts (offline until seen again), and never itself.
    again = PeerService(Agent(Config(), isolated_home), peers.own_id)
    remembered = again.state().peers
    assert [(x.name, x.online) for x in remembered] == [("Den PC", False)]


def test_send_clipboard_from_the_dashboard(isolated_home: Path) -> None:
    clipboard = FakeClipboard("dashboard text")
    app = make_app(isolated_home, clipboard=clipboard)
    write = {"X-LapRemote-Desktop": "1", "Origin": "http://127.0.0.1:7777"}
    with TestClient(app) as client:
        local = TestClient(app, base_url="http://127.0.0.1:7777", client=("127.0.0.1", 5000))
        none_yet = local.post("/desktop/api/clipboard/send", headers=write)
        assert none_yet.json() == {"error": "No owner phone is connected right now."}
        device_id, token, _ = pair_new(client, app)
        with phone(client) as p:
            p.resume(device_id, token)
            assert local.post("/desktop/api/clipboard/send", headers=write).json() == {
                "ok": True,
                "phones": 1,
            }
            assert p.recv_type("clipboard.state", limit=40)["payload"]["text"] == "dashboard text"
        assert local.post("/desktop/api/clipboard/send").status_code == 403
    assert agent_of(app) is not None


def test_big_pages_and_refusing_sites_still_get_icons() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "big.example":
            if request.url.path == "/":
                head = b'<html><head><link rel="icon" href="/i.png"></head><body>'
                return httpx.Response(
                    200, headers={"content-type": "text/html"}, content=head + b"x" * (900 * 1024)
                )
            return httpx.Response(200, content=png_bytes(48))
        # A site that refuses page loads but serves /favicon.ico.
        if request.url.path == "/favicon.ico":
            return httpx.Response(200, content=png_bytes(32))
        return httpx.Response(403)

    async def go(url: str) -> str | None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_site_icon(url, client, public)

    assert asyncio.run(go("https://big.example/")) is not None
    assert asyncio.run(go("https://refuses.example/")) is not None


def test_small_icons_are_scaled_up_to_fill_the_square() -> None:
    icon = decode_icon(png_bytes(16))
    assert icon is not None
    with Image.open(io.BytesIO(base64.b64decode(icon.split(",", 1)[1]))) as image:
        assert image.getbbox() == (0, 0, 96, 96)


def test_a_laptop_that_stops_answering_is_marked_asleep(isolated_home: Path) -> None:
    answers = {"http://192.168.1.40:7777/": True}

    async def checker(url: str) -> bool:
        return answers[url]

    agent = Agent(Config(), isolated_home)
    peers = PeerService(agent, "f" * 16, checker=checker, sender=lambda _m, _t: None)
    sighting = sighting_from(
        txt(id=PEER_ID, name="Den PC", mac="AA:BB:CC:DD:EE:FF"), "192.168.1.40", 7777
    )
    assert sighting is not None

    async def run() -> list[bool]:
        await peers.seen(sighting)
        states = [peers.state().peers[0].online]
        await peers.check_online()
        states.append(peers.state().peers[0].online)
        answers["http://192.168.1.40:7777/"] = False
        await peers.check_online()  # one miss: still online
        states.append(peers.state().peers[0].online)
        await peers.check_online()  # second miss in a row: asleep
        states.append(peers.state().peers[0].online)
        return states

    assert asyncio.run(run()) == [True, True, True, False]
