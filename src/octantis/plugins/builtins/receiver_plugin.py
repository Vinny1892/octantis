"""Built-in OTLP Receiver plugin adapter.

Wraps `octantis.receivers.OTLPReceiver` in the SDK `Receiver` Protocol.
The adapter owns the full lifecycle: `setup()` builds the OTLPReceiver from
settings, `start()/stop()` delegate to the underlying receiver, and `events()`
yields the core `InfraEvent` objects (not SDK Events — the conversion happens
in the main loop where processors need SDK Events).
"""

from __future__ import annotations

from typing import Any

import structlog

from octantis.config import settings
from octantis.receivers import OTLPReceiver

log = structlog.get_logger(__name__)


class OTLPReceiverPlugin:
    """Receiver plugin: manages OTLP gRPC + HTTP servers and the event queue."""

    def __init__(self) -> None:
        self._receiver: OTLPReceiver | None = None

    def setup(self, config: dict[str, Any]) -> None:
        self._receiver = OTLPReceiver(settings.otlp)

    def teardown(self) -> None:
        self._receiver = None

    async def start(self) -> None:
        if self._receiver is None:
            return
        await self._receiver.start()

    async def stop(self) -> None:
        if self._receiver is None:
            return
        await self._receiver.stop()

    async def events(self):
        if self._receiver is None:
            return
        async for event in self._receiver.events():
            yield event

    @property
    def receiver(self) -> OTLPReceiver | None:
        return self._receiver
