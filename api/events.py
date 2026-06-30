"""
Bus d'événements WebSocket — thread-safe.
Le moteur de détection tourne dans un thread séparé ; les envois WebSocket
doivent être planifiés sur la boucle asyncio principale (celle du serveur).
"""

import asyncio
import json
import logging
from typing import Any
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class EventBus:
    """Singleton — broadcast thread-safe vers tous les WebSocket connectés."""

    _instance: "EventBus | None" = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._clients = set()
            cls._instance._loop = None
        return cls._instance

    def set_loop(self, loop):
        """Mémorise la boucle principale (serveur) pour les envois thread-safe."""
        self._loop = loop

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._clients.add(ws)
        logger.info(f"Client connecté ({len(self._clients)} total)")

    def disconnect(self, ws: WebSocket):
        self._clients.discard(ws)
        logger.info(f"Client déconnecté ({len(self._clients)} restants)")

    async def broadcast(self, event_type: str, data: Any):
        """Planifie l'envoi à tous les clients sur la boucle principale (thread-safe)."""
        message = json.dumps({"type": event_type, "data": data})
        for ws in set(self._clients):
            self._schedule_send(ws, message)

    def _schedule_send(self, ws: WebSocket, message: str):
        if self._loop is None:
            return
        try:
            asyncio.run_coroutine_threadsafe(self._safe_send(ws, message), self._loop)
        except Exception:
            pass

    async def _safe_send(self, ws: WebSocket, message: str):
        try:
            await ws.send_text(message)
        except Exception:
            self._clients.discard(ws)

    # Raccourcis
    async def send_dart(self, score_label: str, score_value: int, camera_info: dict):
        await self.broadcast("dart_detected", {
            "label": score_label, "score": score_value, "cameras": camera_info,
        })
        self._ble({"t": "dart", "label": score_label, "value": score_value,
                   "mult": camera_info.get("multiplier", 1),
                   "x": int(camera_info.get("x", 400)),
                   "y": int(camera_info.get("y", 400))})

    async def send_game_state(self, state: dict):
        await self.broadcast("game_state", state)

    async def send_takeout(self):
        await self.broadcast("takeout", {})
        self._ble({"t": "takeout"})

    async def send_camera_status(self, status: dict):
        await self.broadcast("camera_status", status)

    def _ble(self, event: dict):
        """Notifie aussi en BLE (si dispo)."""
        try:
            from api.ble_server import ble_server
            ble_server.notify(event)
        except Exception:
            pass


event_bus = EventBus()
