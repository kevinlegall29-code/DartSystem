"""
Routes de jeu : start, stop, correction, WebSocket temps réel.
"""

import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from api.events import event_bus
from api.game_logic import game, _mult_from_label

logger = logging.getLogger(__name__)

router = APIRouter()


class StartGameRequest(BaseModel):
    mode: str = "501"
    players: list[str]
    double_out: bool = True


class CorrectRequest(BaseModel):
    index: int
    label: str


@router.post("/start")
async def start_game(req: StartGameRequest):
    st = game.start(req.mode, req.players, req.double_out)
    await event_bus.send_game_state(st)
    return st


@router.post("/stop")
async def stop_game():
    game.reset()
    st = game.state()
    await event_bus.send_game_state(st)
    return st


@router.get("/state")
async def game_state():
    return game.state()


@router.post("/next")
async def next_player():
    """Force le passage au joueur suivant (ou retrait manuel)."""
    st = game.end_turn()
    await event_bus.send_game_state(st)
    return st


@router.post("/correct")
async def correct(req: CorrectRequest):
    """Corrige manuellement une fléchette du tour en cours."""
    value = _parse_label(req.label)
    mult = _mult_from_label(req.label)
    st = game.correct_dart(req.index, req.label, value, mult)
    await event_bus.send_game_state(st)
    return st


@router.post("/score/manual")
async def manual_score(req: CorrectRequest):
    """Ajoute manuellement une fléchette (label) — utile si une détection a été ratée."""
    value = _parse_label(req.label)
    mult = _mult_from_label(req.label)
    st = game.register_dart(req.label, value, mult)
    await event_bus.send_game_state(st)
    return st


@router.websocket("/ws")
async def game_ws(ws: WebSocket):
    """WebSocket principal — l'app se connecte ici pour recevoir scores + état jeu."""
    await event_bus.connect(ws)
    try:
        await ws.send_json({"type": "game_state", "data": game.state()})
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=60.0)
            except asyncio.TimeoutError:
                await ws.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        event_bus.disconnect(ws)


def _parse_label(label: str) -> int:
    label = label.upper()
    if label == "DBULL":
        return 50
    if label == "BULL":
        return 25
    if label == "MISS":
        return 0
    prefix = label[0]
    try:
        number = int(label[1:])
    except ValueError:
        return 0
    mult = {"S": 1, "D": 2, "T": 3}.get(prefix, 1)
    return number * mult
