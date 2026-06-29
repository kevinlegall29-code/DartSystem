"""
Routes de jeu : start, stop, score manuel, WebSocket temps réel.
"""

import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
from pydantic import BaseModel

from api.events import event_bus

router = APIRouter()

# État global de la partie (sera remplacé par une classe GameEngine)
_game_state: dict = {
    "active": False,
    "mode": None,          # "501" | "301" | "cricket"
    "players": [],
    "current_player": 0,
    "darts_thrown": 0,
    "scores": {},
}


class StartGameRequest(BaseModel):
    mode: str               # "501" | "301" | "cricket"
    players: list[str]


class ManualScoreRequest(BaseModel):
    label: str              # "T20", "D5", etc.


@router.post("/start")
async def start_game(req: StartGameRequest):
    global _game_state
    _game_state = {
        "active": True,
        "mode": req.mode,
        "players": req.players,
        "current_player": 0,
        "darts_thrown": 0,
        "scores": {p: _starting_score(req.mode) for p in req.players},
    }
    await event_bus.send_game_state(_game_state)
    return {"success": True, "state": _game_state}


@router.post("/stop")
async def stop_game():
    global _game_state
    _game_state["active"] = False
    await event_bus.send_game_state(_game_state)
    return {"success": True}


@router.get("/state")
async def game_state():
    return _game_state


@router.post("/score/manual")
async def manual_score(req: ManualScoreRequest):
    """Correction manuelle du score depuis l'app."""
    score_value = _parse_label(req.label)
    await event_bus.send_dart(req.label, score_value, {"manual": True})
    return {"success": True, "label": req.label, "score": score_value}


@router.post("/takeout")
async def takeout():
    """L'utilisateur retire ses fléchettes (bouton manuel ou détection auto)."""
    global _game_state
    if _game_state["active"]:
        _game_state["darts_thrown"] = 0
        _game_state["current_player"] = (
            (_game_state["current_player"] + 1) % len(_game_state["players"])
        )
    await event_bus.send_takeout()
    await event_bus.send_game_state(_game_state)
    return {"success": True}


@router.websocket("/ws")
async def game_ws(ws: WebSocket):
    """WebSocket principal — l'app Flutter se connecte ici pour recevoir les scores."""
    await event_bus.connect(ws)
    try:
        await ws.send_json({"type": "game_state", "data": _game_state})
        while True:
            try:
                # Attend un message avec timeout — garde la connexion vivante
                await asyncio.wait_for(ws.receive_text(), timeout=60.0)
            except asyncio.TimeoutError:
                # Pas de message depuis 60s, envoie un ping pour vérifier
                await ws.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        event_bus.disconnect(ws)


@router.post("/angle/{value}")
async def set_reference_angle(value: float):
    """Ajuste l'angle de référence du 20 (défaut 81.0). Teste par pas de 9° (= 1 secteur)."""
    import detection.scoring.board_mapping as bm
    bm.REFERENCE_ANGLE_DEG = value
    log_msg = f"Angle référence board : {value}°"
    logger.info(log_msg)
    return {"reference_angle": value}


def _starting_score(mode: str) -> int:
    return {"501": 501, "301": 301, "cricket": 0}.get(mode, 501)


def _parse_label(label: str) -> int:
    """Convertit "T20" → 60, "D5" → 10, "S7" → 7, "BULL" → 25, "DBULL" → 50."""
    label = label.upper()
    if label == "DBULL":
        return 50
    if label == "BULL":
        return 25
    if label == "MISS":
        return 0
    prefix = label[0]
    number = int(label[1:])
    mult = {"S": 1, "D": 2, "T": 3}.get(prefix, 1)
    return number * mult
