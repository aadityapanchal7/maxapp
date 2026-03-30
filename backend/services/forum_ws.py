"""
In-process WebSocket fan-out for forum channel updates (single worker / single process).
For horizontal scaling, replace with Redis pub/sub or similar.
"""

from __future__ import annotations

import asyncio
from typing import Dict, Set

from fastapi import WebSocket
from fastapi.encoders import jsonable_encoder
from starlette.websockets import WebSocketState


class ForumChannelBroker:
    def __init__(self) -> None:
        self._rooms: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, channel_id: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            if channel_id not in self._rooms:
                self._rooms[channel_id] = set()
            self._rooms[channel_id].add(ws)

    async def disconnect(self, channel_id: str, ws: WebSocket) -> None:
        async with self._lock:
            room = self._rooms.get(channel_id)
            if not room:
                return
            room.discard(ws)
            if not room:
                del self._rooms[channel_id]

    async def broadcast(self, channel_id: str, payload: dict) -> None:
        data = jsonable_encoder(payload)
        async with self._lock:
            clients = list(self._rooms.get(channel_id, ()))
        for ws in clients:
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_json(data)
            except Exception:
                pass


forum_channel_broker = ForumChannelBroker()
