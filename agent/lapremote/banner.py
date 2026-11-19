"""Terminal pairing banner: QR code plus the URL and code in text."""

from __future__ import annotations

import io

import qrcode
from qrcode.constants import ERROR_CORRECT_L


def pairing_url(ip: str, port: int, code: str, *, https: bool = False) -> str:
    scheme = "https" if https else "http"
    return f"{scheme}://{ip}:{port}/?pair={code}"


def qr_ascii(data: str) -> str:
    qr = qrcode.QRCode(border=2, error_correction=ERROR_CORRECT_L)
    qr.add_data(data)
    qr.make(fit=True)
    out = io.StringIO()
    qr.print_ascii(out=out, invert=True)
    return out.getvalue()


def render_banner(ip: str | None, port: int, code: str, minutes_valid: int, *, https: bool) -> str:
    lines = ["", "LapRemote is running."]
    if ip is None:
        lines += [
            "Couldn't find this laptop's Wi-Fi address.",
            "Connect to Wi-Fi, then restart LapRemote.",
            f"Pairing code: {code} (valid {minutes_valid} min)",
        ]
        return "\n".join(lines) + "\n"
    url = pairing_url(ip, port, code, https=https)
    lines += [
        "Scan this with your phone's camera to pair:",
        qr_ascii(url),
        f"  {url}",
        f"  Pairing code: {code} (valid {minutes_valid} min, single use)",
        f"  Already paired? Open {'https' if https else 'http'}://{ip}:{port}/ on your phone.",
        "",
    ]
    return "\n".join(lines)
