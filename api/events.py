"""
Bus d'événements WebSocket.
Permet de broadcaster les scores et états à tous les clients connectés (app Flutter).
"""

import asyncio
import json
import logging
from typing import Any
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class EventBus:
    """Singleton — broadcast vers tous les WebSocket connectés."""

    _instance: "EventBus | None" = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._clients: set[WebSocket] = set()
        return cls._instance

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._clients.add(ws)
        logger.info(f"Client connecté ({len(self._clients)} total)")

    def disconnect(self, ws: WebSocket):
        self._clients.discard(ws)
        logger.info(f"Client déconnecté ({len(self._clients)} restants)")

    async def broadcast(self, event_type: str, data: Any):
        """Envoie un événement JSON à tous les clients."""
        message = json.dumps({"type": event_type, "data": data})
        dead = set()
        for ws in self._clients:
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._clients.discard(ws)

    async def send_dart(self, score_label: str, score_value: int, camera_info: dict):
        await self.broadcast("dart_detected", {
            "label": score_label,
            "score": score_value,
            "cameras": camera_info,
        })

    async def send_game_state(self, state: dict):
        await self.broadcast("game_state", state)

    async def send_takeout(self):
        await self.broadcast("takeout", {})

    async def send_camera_status(self, status: dict):
        await self.broadcast("camera_status", status)


event_bus = EventBus()
