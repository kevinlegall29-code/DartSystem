"""
Routes caméras : statut, preview MJPEG, WebSocket live.
"""

import asyncio
import base64
import cv2
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from detection.cameras.stream import CameraManager
from detection import config as cfg
from api.events import event_bus

router = APIRouter()

# Charge l'exposition sauvegardée (défaut 1200)
_config = cfg.load()
_exposure = _config.get("exposure", 1200)

# rotate180 : mettre True pour les caméras montées à l'envers
camera_manager = CameraManager(device_indices=(0, 2, 4), rotate180=(False, True, False))
camera_manager.start_all()

# Applique l'exposition sauvegardée au démarrage
def _apply_exposure(value: int):
    for cam in camera_manager.cameras.values():
        if cam._cap and cam._cap.isOpened():
            cam._cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)
            cam._cap.set(cv2.CAP_PROP_EXPOSURE, value)
            cam.exposure = value

_apply_exposure(_exposure)


@router.get("/status")
async def cameras_status():
    return {"cameras": camera_manager.status()}


@router.get("/debug/{name}")
async def debug_image(name: str):
    """Sert les images de debug (cam0_detect.jpg, cam0_norm.jpg, etc.)."""
    from fastapi.responses import FileResponse, Response
    from pathlib import Path
    path = Path(__file__).parent.parent.parent / "data" / "debug" / name
    if not path.exists() or ".." in name:
        return Response(status_code=404)
    return FileResponse(str(path), media_type="image/jpeg",
                        headers={"Cache-Control": "no-store"})


@router.post("/exposure/{value}")
async def set_exposure(value: int, request=None):
    """Règle et sauvegarde l'exposition. Réinitialise les références du moteur."""
    from api.main import app
    _apply_exposure(value)
    cfg.save({"exposure": value})

    # Réinitialise les références du moteur pour éviter les fausses détections
    try:
        engine = app.state.engine
        await engine._init_references()
    except Exception:
        pass

    return {"exposure": value, "saved": True}


@router.get("/snapshot/{camera_index}")
async def snapshot(camera_index: int):
    cam = camera_manager.cameras.get(camera_index)
    if not cam:
        return {"error": f"Caméra {camera_index} introuvable"}
    img = cam.read()
    if img is None:
        return {"error": "Frame non disponible"}
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return {"image_b64": base64.b64encode(buf).decode(), "camera_index": camera_index}


@router.get("/stream/{camera_index}")
async def mjpeg_stream(camera_index: int):
    async def generate():
        cam = camera_manager.cameras.get(camera_index)
        if cam is None:
            return
        while True:
            frame = cam.read()
            if frame is not None:
                _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"
                )
            await asyncio.sleep(0.1)

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.websocket("/ws")
async def camera_ws(ws: WebSocket):
    await event_bus.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        event_bus.disconnect(ws)
