"""Tracks connected WebSocket clients and broadcasts JSON events to users."""

import json
from collections.abc import Iterable
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    """Keeps a set of live sockets per user (a user may have several tabs open)."""

    def __init__(self) -> None:
        self._sockets: dict[int, set[WebSocket]] = {}

    def is_online(self, user_id: int) -> bool:
        return bool(self._sockets.get(user_id))

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self._sockets.setdefault(user_id, set()).add(websocket)

    def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        sockets = self._sockets.get(user_id)
        if sockets is None:
            return
        sockets.discard(websocket)
        if not sockets:
            self._sockets.pop(user_id, None)

    async def send_to_users(self, user_ids: Iterable[int], event: dict[str, Any]) -> None:
        payload = json.dumps(event)
        for user_id in dict.fromkeys(user_ids):  # dedupe while keeping order
            for socket in list(self._sockets.get(user_id, ())):
                try:
                    await socket.send_text(payload)
                except Exception:
                    # Dead socket: drop it silently.
                    self.disconnect(user_id, socket)

    async def broadcast_all(self, event: dict[str, Any], exclude_user_id: int | None = None) -> None:
        recipients = [user_id for user_id in list(self._sockets) if user_id != exclude_user_id]
        await self.send_to_users(recipients, event)


# Single instance shared by all request handlers.
manager = ConnectionManager()
