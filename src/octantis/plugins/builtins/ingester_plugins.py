# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-transport OTLP ingester plugins (Fork C=1: one plugin per transport, SRP).

Each plugin owns exactly one transport (gRPC or HTTP), its own parser and
event queue, and yields SDK Event instances from that queue via `events()`.
Replaces the unified `OTLPReceiverPlugin` which bundled both transports.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import structlog
from aiohttp import web
from octantis_plugin_sdk import Event as SDKEvent

from octantis.config import settings
from octantis.receivers.grpc_server import create_grpc_server
from octantis.receivers.http_server import _create_routes
from octantis.receivers.parser import OTLPParser

log = structlog.get_logger(__name__)


class _BaseOTLPIngester:
    """Shared queue + lifecycle for per-transport OTLP ingesters."""

    name: str = ""

    def __init__(self) -> None:
        self._parser: OTLPParser | None = None
        self._queue: asyncio.Queue[SDKEvent] | None = None
        self._stopped = False

    def setup(self, config: dict[str, Any]) -> None:
        self._parser = OTLPParser()
        self._queue = asyncio.Queue(maxsize=settings.otlp.queue_max_size)
        self._stopped = False

    def teardown(self) -> None:
        self._parser = None
        self._queue = None

    async def events(self) -> AsyncIterator[SDKEvent]:
        if self._queue is None:
            return
        watermark_threshold = self._queue.maxsize // 2 if self._queue.maxsize else 0
        watermark_logged = False
        while True:
            if self._stopped and self._queue.empty():
                return
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except TimeoutError:
                if self._stopped:
                    return
                continue
            qsize = self._queue.qsize()
            if watermark_threshold and qsize > watermark_threshold and not watermark_logged:
                log.warning("otlp.queue.high_watermark", ingester=self.name, queue_size=qsize)
                watermark_logged = True
            elif qsize <= watermark_threshold:
                watermark_logged = False
            yield event


class OTLPGrpcIngester(_BaseOTLPIngester):
    """Ingester plugin: OTLP gRPC transport."""

    name = "otlp-grpc"

    def __init__(self) -> None:
        super().__init__()
        self._server: Any = None

    async def start(self) -> None:
        if not settings.otlp.grpc_enabled:
            log.info("otlp.grpc.disabled")
            return
        assert self._queue is not None and self._parser is not None
        self._server = await create_grpc_server(self._queue, self._parser, settings.otlp.grpc_port)
        await self._server.start()
        log.info("otlp.grpc.started", port=settings.otlp.grpc_port)

    async def stop(self) -> None:
        self._stopped = True
        if self._server is not None:
            await self._server.stop(grace=5)
            self._server = None
        log.info("otlp.grpc.stopped")


class OTLPHttpIngester(_BaseOTLPIngester):
    """Ingester plugin: OTLP HTTP transport."""

    name = "otlp-http"

    def __init__(self) -> None:
        super().__init__()
        self._runner: web.AppRunner | None = None

    async def start(self) -> None:
        if not settings.otlp.http_enabled:
            log.info("otlp.http.disabled")
            return
        assert self._queue is not None and self._parser is not None
        app = _create_routes(self._queue, self._parser)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", settings.otlp.http_port)
        await site.start()
        log.info("otlp.http.started", port=settings.otlp.http_port)

    async def stop(self) -> None:
        self._stopped = True
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
        log.info("otlp.http.stopped")
