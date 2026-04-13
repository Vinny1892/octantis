# SPDX-License-Identifier: AGPL-3.0-or-later
"""OTLPReceiver — orchestrates gRPC + HTTP servers and the event queue."""

import asyncio
from collections.abc import AsyncIterator

import structlog
from aiohttp import web

from octantis.config import OTLPSettings
from octantis.models.event import InfraEvent
from octantis.receivers.grpc_server import create_grpc_server
from octantis.receivers.http_server import _create_routes
from octantis.receivers.parser import OTLPParser

log = structlog.get_logger(__name__)


class OTLPReceiver:
    """Manages OTLP gRPC + HTTP servers and an asyncio.Queue of InfraEvent."""

    def __init__(self, config: OTLPSettings) -> None:
        self._config = config
        self._parser = OTLPParser()
        self._queue: asyncio.Queue[InfraEvent] = asyncio.Queue(maxsize=config.queue_max_size)
        self._grpc_server = None
        self._http_runner: web.AppRunner | None = None
        self._stopped = False

    async def start(self) -> None:
        if not self._config.grpc_enabled and not self._config.http_enabled:
            log.warning("otlp.server.no_transports")

        if self._config.grpc_enabled:
            self._grpc_server = await create_grpc_server(
                self._queue, self._parser, self._config.grpc_port
            )
            await self._grpc_server.start()
        else:
            log.info("otlp.grpc.disabled")

        if self._config.http_enabled:
            app = _create_routes(self._queue, self._parser)
            self._http_runner = web.AppRunner(app)
            await self._http_runner.setup()
            site = web.TCPSite(self._http_runner, "0.0.0.0", self._config.http_port)
            await site.start()
        else:
            log.info("otlp.http.disabled")

        log.info(
            "otlp.server.started",
            grpc_port=self._config.grpc_port if self._config.grpc_enabled else None,
            http_port=self._config.http_port if self._config.http_enabled else None,
            queue_max_size=self._config.queue_max_size,
        )

    async def stop(self) -> None:
        self._stopped = True
        if self._grpc_server:
            await self._grpc_server.stop(grace=5)
        if self._http_runner:
            await self._http_runner.cleanup()
        log.info("otlp.server.stopped")

    async def events(self) -> AsyncIterator[InfraEvent]:
        """Yield InfraEvent objects from the queue."""
        watermark_threshold = self._config.queue_max_size // 2
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

            # High watermark warning
            qsize = self._queue.qsize()
            if qsize > watermark_threshold and not watermark_logged:
                log.warning("otlp.queue.high_watermark", queue_size=qsize)
                watermark_logged = True
            elif qsize <= watermark_threshold:
                watermark_logged = False

            yield event
