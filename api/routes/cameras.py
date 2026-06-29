"""
Routes caméras : statut, preview MJPEG, WebSocket live.
"""

import asyncio
import base64
import cv2
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from detection.cameras.stream import CameraManager
from api.events import event_bus

router = APIRouter()

camera_manager = CameraManager(indices=(0, 1, 2))
camera_manager.start_all()


@router.get("/status")
async def cameras_status():
    return {"cameras": camera_manager.status()}


@router.post("/exposure/{value}")
async def set_exposure(value: int):
    """Règle l'exposition sur toutes les caméras (valeur V4L2, typiquement 50–500)."""
    results = {}
    for idx, cam in camera_manager.cameras.items():
        if cam._cap and cam._cap.isOpened():
            cam._cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)
            ok = cam._cap.set(cv2.CAP_PROP_EXPOSURE, value)
            cam.exposure = value
            results[idx] = "ok" if ok else "erreur"
        else:
            results[idx] = "non disponible"
    return {"exposure": value, "cameras": results}


@router.get("/snapshot/{camera_index}")
async def snapshot(camera_index: int):
    """Retourne une frame JPEG en base64 pour la caméra donnée."""
    frame = camera_manager.cameras.get(camera_index, {})
    if not frame:
        return {"error": f"Caméra {camera_index} introuvable"}
    img = camera_manager.cameras[camera_index].read()
    if img is None:
        return {"error": "Frame non disponible"}
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return {"image_b64": base64.b64encode(buf).decode(), "camera_index": camera_index}


@router.get("/stream/{camera_index}")
async def mjpeg_stream(camera_index: int):
    """Stream MJPEG pour prévisualisation en temps réel (calibration UI)."""

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
            await asyncio.sleep(0.033)   # ~30 fps

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.websocket("/ws")
async def camera_ws(ws: WebSocket):
    """WebSocket de statut caméras (utilisé par l'app pour la supervision)."""
    await event_bus.connect(ws)
    try:
        while True:
            await ws.receive_text()   # Maintient la connexion
    except WebSocketDisconnect:
        event_bus.disconnect(ws)
