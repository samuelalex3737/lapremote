"""Message router: envelope parsing, auth and role checks, validation, rate limits, dispatch.

Bad input never closes the connection: it gets ``ack ok:false`` with a short reason.
"""

from __future__ import annotations

import asyncio
import json
import logging
import statistics
import time
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import ValidationError

from lapremote.connection import Connection
from lapremote.logging_setup import get_logger, log_event
from lapremote.protocol import (
    CLIENT_MESSAGES,
    MAX_MESSAGE_BYTES,
    Ack,
    AuthFail,
    AuthFailReason,
    ClientMessage,
    Envelope,
    WireModel,
)

Handler = Callable[[Connection, Any], Awaitable[None]]

# Fire-and-forget types are logged at DEBUG so 120 moves/s do not flood the log.
HIGH_FREQUENCY = frozenset({"input.move", "input.scroll", "preview.ack"})
# Types whose payload length (never content) is logged.
LENGTH_LOGGED = {"key.text": "text", "ai.command": "text"}

MSG_INVALID = "That message wasn't valid."
MSG_UNKNOWN = "Unknown request."
MSG_NOT_PAIRED = "Pair this phone first."
MSG_ALREADY_PAIRED = "Already connected."
MSG_OWNER_ONLY = "Only the owner can do that."
MSG_SLOW_DOWN = "Too many requests. Slow down a little."
MSG_UNAVAILABLE = "That isn't available on this laptop yet."
MSG_INTERNAL = "Something went wrong on the laptop."
MSG_PAUSED = "Remote control is paused on the laptop."

# Still answered while remote control is paused: staying connected and seeing state.
PAUSE_EXEMPT = frozenset(
    {"auth.pair", "auth.resume", "ping", "devices.list", "media.artwork", "preview.stop"}
)
TIMING_SAMPLES = 200


class ActionError(Exception):
    """A handler failure with a short, friendly message for the phone."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class AuthRejectedError(Exception):
    def __init__(self, reason: AuthFailReason) -> None:
        super().__init__(reason)
        self.reason = reason


def _describe(error: ValidationError) -> str:
    first = error.errors()[0]
    where = ".".join(str(p) for p in first.get("loc", ())) or "payload"
    return f"Invalid {where}: {first.get('msg', 'bad value')}"[:160]


class Router:
    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._handlers: dict[str, Handler] = {}
        self._background_types: set[str] = set()
        self.is_paused: Callable[[], bool] = lambda: False
        self._timings: dict[str, deque[float]] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._log = logger or get_logger("router")

    def register(self, type_: str, handler: Handler, *, background: bool = False) -> None:
        """Register a handler. ``background`` handlers (slow ones, like the AI planner)
        run beside the connection's later messages instead of holding them up."""
        if type_ not in CLIENT_MESSAGES:
            msg = f"{type_!r} is not a client message in protocol.py"
            raise KeyError(msg)
        self._handlers[type_] = handler
        if background:
            self._background_types.add(type_)
        else:
            self._background_types.discard(type_)

    def handling_ms(self, device_id: str) -> tuple[float, float] | None:
        """Median and 95th percentile time the laptop took to handle this device's commands."""
        samples = sorted(self._timings.get(device_id, ()))
        if not samples:
            return None
        p95 = samples[min(len(samples) - 1, round(0.95 * (len(samples) - 1)))]
        return round(statistics.median(samples), 2), round(p95, 2)

    def has_handler(self, type_: str) -> bool:
        return type_ in self._handlers

    async def _ack(self, conn: Connection, msg_id: str, ok: bool, error: str | None = None) -> None:
        await conn.send("ack", Ack(id=msg_id, ok=ok, error=error))

    def _record(
        self, conn: Connection, type_: str, ok: bool, started: float, **fields: Any
    ) -> None:
        level = logging.DEBUG if type_ in HIGH_FREQUENCY and ok else logging.INFO
        log_event(
            self._log,
            "command",
            level=level,
            type=type_,
            device=conn.device_id,
            conn=conn.conn_id,
            ok=ok,
            ms=round((time.perf_counter() - started) * 1000, 2),
            **fields,
        )

    async def handle_text(self, conn: Connection, text: str) -> None:
        started = time.perf_counter()
        if len(text) > MAX_MESSAGE_BYTES:
            self._record(conn, "?", False, started, error="too_large", bytes=len(text))
            await self._ack(conn, "", False, MSG_INVALID)
            return
        try:
            raw = json.loads(text)
        except ValueError:
            self._record(conn, "?", False, started, error="bad_json")
            await self._ack(conn, "", False, MSG_INVALID)
            return
        raw_id = raw.get("id") if isinstance(raw, dict) else None
        reply_id = raw_id if isinstance(raw_id, str) and len(raw_id) <= 64 else ""
        try:
            envelope = Envelope.model_validate(raw)
        except ValidationError:
            self._record(conn, "?", False, started, error="bad_envelope")
            await self._ack(conn, reply_id, False, MSG_INVALID)
            return
        await self._dispatch(conn, envelope, started)

    async def _dispatch(self, conn: Connection, env: Envelope, started: float) -> None:
        type_ = env.type
        spec = CLIENT_MESSAGES.get(type_)
        if spec is None:
            self._record(conn, type_[:64], False, started, error="unknown_type")
            await self._ack(conn, env.id, False, MSG_UNKNOWN)
            return

        if not conn.messages.allow():
            self._record(conn, type_, False, started, error="rate_limited")
            if spec.reply != "none":
                await self._ack(conn, env.id, False, MSG_SLOW_DOWN)
            return

        denial = self._check_access(conn, spec)
        if denial is not None:
            self._record(conn, type_, False, started, error="denied")
            await self._ack(conn, env.id, False, denial)
            return

        if type_ not in PAUSE_EXEMPT and self.is_paused():
            self._record(conn, type_, False, started, error="paused")
            if spec.reply != "none":
                await self._ack(conn, env.id, False, MSG_PAUSED)
            return

        try:
            payload = spec.payload.model_validate(env.payload)
        except ValidationError as exc:
            self._record(conn, type_, False, started, error="invalid_payload")
            await self._ack(conn, env.id, False, _describe(exc))
            return

        extra = self._lengths(type_, payload)
        if type_ == "key.text" and not conn.key_text.allow():
            self._record(conn, type_, False, started, error="rate_limited", **extra)
            await self._ack(conn, env.id, False, MSG_SLOW_DOWN)
            return

        handler = self._handlers.get(type_)
        if handler is None:
            self._record(conn, type_, False, started, error="unavailable", **extra)
            await self._ack(conn, env.id, False, MSG_UNAVAILABLE)
            return

        if type_ in self._background_types:
            task = asyncio.get_running_loop().create_task(
                self._run_handler(conn, env, spec, handler, payload, started, extra)
            )
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
            return
        await self._run_handler(conn, env, spec, handler, payload, started, extra)

    async def _run_handler(
        self,
        conn: Connection,
        env: Envelope,
        spec: ClientMessage,
        handler: Handler,
        payload: WireModel,
        started: float,
        extra: dict[str, Any],
    ) -> None:
        type_ = env.type
        try:
            await handler(conn, payload)
        except AuthRejectedError as exc:
            self._record(conn, type_, False, started, error=exc.reason)
            await conn.send("auth.fail", AuthFail(reason=exc.reason))
            return
        except ActionError as exc:
            self._record(conn, type_, False, started, error=exc.message, **extra)
            await self._ack(conn, env.id, False, exc.message)
            return
        except Exception:
            self._log.exception("handler_crashed", extra={"fields": {"type": type_}})
            self._record(conn, type_, False, started, error="internal", **extra)
            await self._ack(conn, env.id, False, MSG_INTERNAL)
            return

        self._record(conn, type_, True, started, **extra)
        if conn.device_id is not None and type_ not in HIGH_FREQUENCY:
            samples = self._timings.setdefault(conn.device_id, deque(maxlen=TIMING_SAMPLES))
            samples.append((time.perf_counter() - started) * 1000)
        if spec.reply == "ack":
            await self._ack(conn, env.id, True)

    @staticmethod
    def _check_access(conn: Connection, spec: ClientMessage) -> str | None:
        if spec.role == "none":
            return MSG_ALREADY_PAIRED if conn.authed else None
        if not conn.authed:
            return MSG_NOT_PAIRED
        if spec.role == "owner" and conn.role != "owner":
            return MSG_OWNER_ONLY
        return None

    @staticmethod
    def _lengths(type_: str, payload: WireModel) -> dict[str, int]:
        field = LENGTH_LOGGED.get(type_)
        if field is None:
            return {}
        value = getattr(payload, field, "")
        return {"textLength": len(value) if isinstance(value, str) else 0}
