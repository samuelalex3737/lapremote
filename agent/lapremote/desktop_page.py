"""HTML for the /desktop dashboard (``assets/dashboard.html``). Self-contained: no external
files, fonts or scripts.

``__NONCE__`` is replaced per response and matches the Content-Security-Policy. Text from
phones (device names) is only ever set with textContent, never parsed as HTML.
"""

from pathlib import Path

DASHBOARD_HTML = (Path(__file__).parent / "assets" / "dashboard.html").read_text(encoding="utf-8")
