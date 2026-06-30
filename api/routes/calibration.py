"""
Routes de calibration : distorsion (damier) et board (4 points).
"""

import base64
import cv2
import numpy as np
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from detection.calibration.board import (
    compute_homography, compute_homography_advanced, advanced_point_targets,
    normalize_frame, validate_calibration,
    save_board_calibration, load_board_calibration,
)
from detection.calibration.lens import load_lens_calibration, undistort

router = APIRouter()
DATA_DIR = Path(__file__).parent.parent.parent / "data" / "calibrations"


class CalibPoint(BaseModel):
    x: float
    y: float


class BoardCalibRequest(BaseModel):
    camera_index: int
    points: dict[str, CalibPoint]   # {"20_1": {x,y}, "6_10": {x,y}, ...}


class AdvPoint(BaseModel):
    i: int          # index de la frontière (0–19)
    x: float
    y: float


class AdvBoardCalibRequest(BaseModel):
    camera_index: int
    points: list[AdvPoint]   # ≥ 4 points indexés


def _undistort_cam_frame(camera_index: int):
    """Lit une frame de la caméra et corrige la distorsion si dispo."""
    from api.routes.cameras import camera_manager
    frame = camera_manager.cameras[camera_index].read()
    if frame is None:
        raise HTTPException(503, f"Caméra {camera_index} non disponible")
    try:
        K, D = load_lens_calibration(camera_index, DATA_DIR)
        frame = undistort(frame, K, D)
    except FileNotFoundError:
        pass
    return frame


@router.post("/board")
async def calibrate_board(req: BoardCalibRequest):
    """
    Reçoit les 4 points cliqués depuis l'app Flutter,
    calcule l'homographie et retourne la vue normalisée en JPEG base64.
    """
    from api.routes.cameras import camera_manager

    src_points = {k: (v.x, v.y) for k, v in req.points.items()}

    required_keys = {"20_1", "6_10", "3_19", "11_14"}
    if not required_keys.issubset(src_points.keys()):
        raise HTTPException(400, f"Points manquants. Requis : {required_keys}")

    H = compute_homography(src_points)

    # Récupère une frame de la caméra concernée
    frame = camera_manager.cameras[req.camera_index].read()
    if frame is None:
        raise HTTPException(503, f"Caméra {req.camera_index} non disponible")

    # Corrige la distorsion si calibration disponible
    try:
        K, D = load_lens_calibration(req.camera_index, DATA_DIR)
        frame = undistort(frame, K, D)
    except FileNotFoundError:
        pass  # Pas de calibration distorsion, on continue

    normalized = normalize_frame(frame, H)
    validation = validate_calibration(normalized)

    save_board_calibration(req.camera_index, src_points, H, validation, DATA_DIR)

    # Encode la vue normalisée en JPEG base64 pour l'app
    _, buf = cv2.imencode(".jpg", normalized, [cv2.IMWRITE_JPEG_QUALITY, 85])
    img_b64 = base64.b64encode(buf).decode()

    return {
        "success": True,
        "camera_index": req.camera_index,
        "validation": validation,
        "normalized_image_b64": img_b64,
    }


@router.get("/board/advanced/plan")
async def advanced_plan():
    """Séquence des points de la calibration avancée (pour guider l'UI)."""
    targets = advanced_point_targets()
    return {"points": [
        {"i": i, "label": t["label"], "ring": t["ring"]}
        for i, t in sorted(targets.items())
    ]}


@router.post("/board/advanced")
async def calibrate_board_advanced(req: AdvBoardCalibRequest):
    """
    Calibration avancée : N points (frontières aux anneaux double/triple) →
    homographie par moindres carrés (plus précise et robuste que 4 points).
    """
    pts = [{"i": p.i, "x": p.x, "y": p.y} for p in req.points]
    try:
        H = compute_homography_advanced(pts)
    except ValueError as e:
        raise HTTPException(400, str(e))

    frame = _undistort_cam_frame(req.camera_index)
    normalized = normalize_frame(frame, H)
    validation = validate_calibration(normalized)

    # Sauvegarde (src_points = liste indexée, pour pouvoir relire/refaire)
    src_points = {str(p.i): {"x": p.x, "y": p.y} for p in req.points}
    save_board_calibration(req.camera_index, src_points, H, validation, DATA_DIR)

    _, buf = cv2.imencode(".jpg", normalized, [cv2.IMWRITE_JPEG_QUALITY, 85])
    img_b64 = base64.b64encode(buf).decode()

    return {
        "success": True,
        "camera_index": req.camera_index,
        "points_used": len(req.points),
        "validation": validation,
        "normalized_image_b64": img_b64,
    }


@router.post("/lens/capture/{camera_index}")
async def lens_capture_frame(camera_index: int):
    """Capture une frame et tente de détecter le damier (distorsion)."""
    from api.routes.cameras import camera_manager
    from detection.calibration.lens import lens_capture
    cam = camera_manager.cameras.get(camera_index)
    if cam is None:
        raise HTTPException(503, f"Caméra {camera_index} indisponible")
    frame = cam.read()
    if frame is None:
        raise HTTPException(503, "Frame indisponible")
    found, count = lens_capture(camera_index, frame)
    return {"found": found, "count": count}


@router.post("/lens/compute/{camera_index}")
async def lens_compute_cam(camera_index: int):
    """Calcule et sauvegarde la calibration distorsion de la caméra."""
    from detection.calibration.lens import lens_compute
    try:
        result = lens_compute(camera_index, DATA_DIR)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"success": True, "reprojection_error": result["reprojection_error"],
            "captures": result["captures_used"]}


@router.post("/lens/reset/{camera_index}")
async def lens_reset_cam(camera_index: int):
    from detection.calibration.lens import lens_reset, lens_count
    lens_reset(camera_index)
    return {"count": lens_count(camera_index)}


@router.get("/status")
async def calibration_status():
    """Retourne le statut de calibration de chaque caméra."""
    status = {}
    for cam_idx in range(3):
        lens_ok = (DATA_DIR / f"lens_cam{cam_idx}.json").exists()
        board_ok = (DATA_DIR / f"board_cam{cam_idx}.json").exists()
        status[str(cam_idx)] = {
            "lens": lens_ok,
            "board": board_ok,
            "ready": lens_ok and board_ok,
        }
    return status


@router.delete("/board/{camera_index}")
async def reset_board_calibration(camera_index: int):
    path = DATA_DIR / f"board_cam{camera_index}.json"
    if path.exists():
        path.unlink()
    return {"success": True}
