"""FastAPI application factory for the agent.

Phase 0 exposes only the HTTP health check. The /ws endpoint, static hosting
and pairing are added in Phase 1.
"""

from __future__ import annotations

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from lapremote import __version__
from lapremote.system.platform_info import OsName, detect_os


class HealthResponse(BaseModel):
    app: Literal["lapremote"]
    version: str
    os: OsName


def create_app() -> FastAPI:
    app = FastAPI(
        title="LapRemote agent",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    os_name = detect_os()

    @app.get("/api/health")
    async def health() -> HealthResponse:
        return HealthResponse(app="lapremote", version=__version__, os=os_name)

    return app
