"""Screen capture with mss, scaled JPEG frames, and per-connection streaming.

Frames go out as binary WebSocket messages: an 8-byte big-endian header
(uint32 frame number, uint32 monitor index) followed by the JPEG. A phone acks
each frame it has drawn; the agent never has more than 2 unacknowledged frames in
flight and simply skips capturing while the phone is behind.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import struct
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Protocol

from PIL import Image

from lapremote.connection import Connection
from lapremote.core import Agent
from lapremote.logging_setup import get_logger, log_event
from lapremote.protocol import (
    PREVIEW_HEADER_FORMAT,
    Empty,
    MonitorInfo,
    PreviewAck,
    PreviewMeta,
    PreviewStart,
)
from lapremote.router import ActionError

log = get_logger("preview")

MAX_IN_FLIGHT = 2


@dataclass(frozen=True)
class Monitor:
    index: int
    left: int
    top: int
    width: int
    height: int
    primary: bool

    def to_wire(self) -> MonitorInfo:
        return MonitorInfo(
            index=self.index,
            left=self.left,
            top=self.top,
            width=self.width,
            height=self.height,
            primary=self.primary,
        )


@dataclass(frozen=True)
class Frame:
    jpeg: bytes
    width: int
    height: int


class Grabber(Protocol):
    def monitors(self) -> list[Monitor]: ...
    def grab(self, monitor: int, width: int, quality: int) -> Frame: ...


def scaled_size(src_w: int, src_h: int, width: int) -> tuple[int, int]:
    """Output size for a target width, keeping the aspect ratio and never upscaling."""
    out_w = min(width, src_w)
    out_h = max(1, round(src_h * out_w / src_w))
    return out_w, out_h


def encode_frame(
    pixels: bytes, size: tuple[int, int], width: int, quality: int, raw_mode: str = "RGB"
) -> Frame:
    """Scale and JPEG-encode raw pixels. ``raw_mode`` "BGRX" decodes mss shots natively."""
    img = Image.frombytes("RGB", size, pixels, "raw", raw_mode)
    out = scaled_size(size[0], size[1], width)
    if out != size:
        # A whole-number box reduce first is far cheaper than resizing the full frame.
        factor = size[0] // out[0]
        if factor >= 2:
            img = img.reduce(factor)
        if img.size != out:
            img = img.resize(out, Image.Resampling.BILINEAR)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return Frame(buf.getvalue(), out[0], out[1])


def pack_frame(frame_no: int, monitor: int, jpeg: bytes) -> bytes:
    return struct.pack(PREVIEW_HEADER_FORMAT, frame_no & 0xFFFFFFFF, monitor) + jpeg


class MssGrabber:
    """mss on one dedicated thread (mss handles are not shared across threads)."""

    def __init__(self) -> None:
        self._local = threading.local()

    def _mss(self) -> Any:
        sct = getattr(self._local, "sct", None)
        if sct is None:
            import mss  # noqa: PLC0415

            sct = mss.MSS()
            self._local.sct = sct
        return sct

    def monitors(self) -> list[Monitor]:
        raw = self._mss().monitors[1:]  # index 0 is the union of all monitors
        found = []
        for i, mon in enumerate(raw):
            found.append(
                Monitor(
                    index=i,
                    left=int(mon["left"]),
                    top=int(mon["top"]),
                    width=int(mon["width"]),
                    height=int(mon["height"]),
                    primary=int(mon["left"]) == 0 and int(mon["top"]) == 0,
                )
            )
        return found

    def grab(self, monitor: int, width: int, quality: int) -> Frame:
        sct = self._mss()
        shot = sct.grab(sct.monitors[monitor + 1])
        return encode_frame(shot.bgra, shot.size, width, quality, raw_mode="BGRX")


class PreviewStream:
    """One phone's preview: a capture loop at `fps` with at most 2 frames in flight."""

    def __init__(
        self,
        conn: Connection,
        run: Callable[[Callable[[], Frame]], Any],
        grabber: Grabber,
        request: PreviewStart,
        quality: int,
    ) -> None:
        self.conn = conn
        self._run = run
        self._grabber = grabber
        self.monitor = request.monitor
        self.width = request.width
        self.interval = 1 / request.fps
        self.quality = quality
        self.sent = 0
        self.acked = 0
        self.skipped = 0
        self.bytes_sent = 0
        self._task: asyncio.Task[None] | None = None

    @property
    def in_flight(self) -> int:
        return self.sent - self.acked

    def ack(self, frame: int) -> None:
        if frame > self.acked and frame <= self.sent:
            self.acked = frame

    def start(self) -> None:
        self._task = asyncio.get_running_loop().create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _loop(self) -> None:
        while not self.conn.closed:
            started = time.perf_counter()
            if self.in_flight >= MAX_IN_FLIGHT:
                self.skipped += 1
            else:
                await self.send_one()
            elapsed = time.perf_counter() - started
            await asyncio.sleep(max(0.0, self.interval - elapsed))

    async def send_one(self) -> None:
        try:
            frame = await self._run(
                lambda: self._grabber.grab(self.monitor, self.width, self.quality)
            )
        except Exception as exc:  # the screen can vanish (unplugged monitor, locked session)
            log_event(log, "capture_failed", level=30, error=repr(exc))
            await asyncio.sleep(1.0)
            return
        self.sent += 1
        data = pack_frame(self.sent, self.monitor, frame.jpeg)
        if await self.conn.send_bytes(data):
            self.bytes_sent += len(data)


class PreviewService:
    def __init__(self, agent: Agent, grabber: Grabber | None) -> None:
        self._agent = agent
        self._grabber = grabber
        self._streams: dict[str, PreviewStream] = {}
        # A single capture thread keeps one mss handle for its whole life.
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="preview")

    def register(self) -> None:
        if self._grabber is None:
            self._agent.set_feature(
                "preview", False, "Screen capture isn't available on this laptop."
            )
            return
        self._agent.set_feature("preview", True)
        router = self._agent.router
        router.register("preview.start", self._start)
        router.register("preview.stop", self._stop)
        router.register("preview.ack", self._ack)
        self._agent.on_disconnect.append(self._dropped)
        self._agent.on_shutdown.append(self.close)

    async def monitors(self) -> list[Monitor]:
        """Current monitor layout (read on the capture thread)."""
        grabber = self._grabber
        if grabber is None:
            return []
        return await asyncio.get_running_loop().run_in_executor(self._executor, grabber.monitors)

    def stream_for(self, conn: Connection) -> PreviewStream | None:
        return self._streams.get(conn.conn_id)

    async def _run(self, fn: Callable[[], Frame]) -> Frame:
        return await asyncio.get_running_loop().run_in_executor(self._executor, fn)

    async def _start(self, conn: Connection, p: PreviewStart) -> None:
        grabber = self._grabber
        if grabber is None:
            raise ActionError("Screen capture isn't available on this laptop.")
        monitors = await self.monitors()
        if not 0 <= p.monitor < len(monitors):
            raise ActionError("That screen isn't connected anymore.")
        await self._stop_stream(conn)
        quality = self._agent.config.preview.quality
        stream = PreviewStream(conn, self._run, grabber, p, quality)
        self._streams[conn.conn_id] = stream
        mon = monitors[p.monitor]
        out_w, out_h = scaled_size(mon.width, mon.height, p.width)
        await conn.send(
            "preview.meta",
            PreviewMeta(width=out_w, height=out_h, monitors=[m.to_wire() for m in monitors]),
        )
        stream.start()
        log_event(
            log, "preview_started", conn=conn.conn_id, fps=p.fps, width=p.width, monitor=p.monitor
        )

    async def _stop_stream(self, conn: Connection) -> None:
        stream = self._streams.pop(conn.conn_id, None)
        if stream is not None:
            await stream.stop()
            log_event(
                log,
                "preview_stopped",
                conn=conn.conn_id,
                sent=stream.sent,
                skipped=stream.skipped,
                bytes=stream.bytes_sent,
            )

    async def _stop(self, conn: Connection, _p: Empty) -> None:
        await self._stop_stream(conn)

    async def _ack(self, conn: Connection, p: PreviewAck) -> None:
        stream = self._streams.get(conn.conn_id)
        if stream is not None:
            stream.ack(p.frame)

    async def _dropped(self, conn: Connection) -> None:
        await self._stop_stream(conn)

    async def close(self) -> None:
        for conn_id in list(self._streams):
            stream = self._streams.pop(conn_id)
            await stream.stop()
        self._executor.shutdown(wait=False, cancel_futures=True)


def create_grabber() -> Grabber | None:
    """The mss grabber, or None when no screen can be captured (for example no display)."""
    grabber = MssGrabber()
    try:
        if not grabber.monitors():
            return None
    except Exception as exc:
        log_event(log, "capture_unavailable", level=30, error=repr(exc))
        return None
    return grabber
