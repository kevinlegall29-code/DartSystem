"""
Calibration de la distorsion des lentilles via damier OpenCV.
À faire une seule fois par caméra après installation physique.
"""

import cv2
import numpy as np
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CHECKERBOARD = (8, 5)       # Coins intérieurs du damier 9×6 (cases - 1)
MIN_CAPTURES = 12           # Minimum pour une bonne calibration
MAX_REPROJ_ERROR = 1.0      # Erreur de reprojection acceptable (pixels)


# --- Calibration headless (pilotée par le web) ---------------------------------
# Accumulateur par caméra : {cam_idx: {"objpoints": [...], "imgpoints": [...], "shape": (w,h)}}
_accum: dict = {}


def _objp_for(size: tuple[int, int]):
    objp = np.zeros((size[0] * size[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0:size[0], 0:size[1]].T.reshape(-1, 2)
    return objp


def _find_board(gray):
    """Détection robuste du damier. Essaie SB puis classique, dans les 2 orientations.
    Retourne (found, corners, size_utilisée)."""
    sizes = [CHECKERBOARD, (CHECKERBOARD[1], CHECKERBOARD[0])]  # (8,5) et (5,8)

    # 1) Détecteur moderne SB (le plus robuste) si disponible
    if hasattr(cv2, "findChessboardCornersSB"):
        for sz in sizes:
            try:
                found, corners = cv2.findChessboardCornersSB(
                    gray, sz, flags=cv2.CALIB_CB_NORMALIZE_IMAGE)
            except cv2.error:
                found = False
            if found:
                return True, corners, sz

    # 2) Fallback classique avec rehaussement de contraste (CLAHE)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    flags = cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE
    for src in (gray, enhanced):
        for sz in sizes:
            found, corners = cv2.findChessboardCorners(src, sz, flags)
            if found:
                criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
                corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
                return True, corners, sz
    return False, None, None


def lens_capture(cam_idx: int, frame: np.ndarray) -> tuple[bool, int]:
    """Détecte le damier sur une frame. Si trouvé, l'ajoute. Retourne (trouvé, nb_total)."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    acc = _accum.setdefault(cam_idx, {"objpoints": [], "imgpoints": [], "shape": gray.shape[::-1]})
    found, corners, sz = _find_board(gray)
    if not found:
        return False, len(acc["objpoints"])
    acc["objpoints"].append(_objp_for(sz))
    acc["imgpoints"].append(corners)
    acc["shape"] = gray.shape[::-1]
    return True, len(acc["objpoints"])


def lens_count(cam_idx: int) -> int:
    return len(_accum.get(cam_idx, {}).get("objpoints", []))


def lens_reset(cam_idx: int):
    _accum.pop(cam_idx, None)


def lens_compute(cam_idx: int, output_dir: Path) -> dict:
    """Calcule et sauvegarde la calibration distorsion à partir des captures accumulées."""
    acc = _accum.get(cam_idx)
    if not acc or len(acc["objpoints"]) < MIN_CAPTURES:
        n = len(acc["objpoints"]) if acc else 0
        raise ValueError(f"Pas assez de captures ({n}/{MIN_CAPTURES} minimum)")

    error, K, D, _, _ = cv2.calibrateCamera(
        acc["objpoints"], acc["imgpoints"], acc["shape"], None, None)

    result = {
        "camera_index": cam_idx,
        "image_size": list(acc["shape"]),
        "reprojection_error": round(float(error), 4),
        "camera_matrix": K.tolist(),
        "dist_coefficients": D.tolist(),
        "captures_used": len(acc["objpoints"]),
    }
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / f"lens_cam{cam_idx}.json", "w") as f:
        json.dump(result, f, indent=2)
    lens_reset(cam_idx)
    logger.info(f"Calibration distorsion cam{cam_idx} sauvée — erreur {error:.3f}px")
    return result


def collect_calibration_frames(camera_index: int, target: int = 15) -> list:
    """
    Capture interactive des frames du damier.
    ESPACE = capturer, Q = terminer.
    Retourne la liste des frames valides.
    """
    objp = np.zeros((CHECKERBOARD[0] * CHECKERBOARD[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0:CHECKERBOARD[0], 0:CHECKERBOARD[1]].T.reshape(-1, 2)

    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)

    objpoints, imgpoints = [], []
    img_shape = None

    cap = cv2.VideoCapture(camera_index, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    print(f"\nCalibration distorsion — Caméra {camera_index}")
    print("  → Déplacez le damier dans toutes les positions/angles")
    print("  → ESPACE : capturer (quand cadre vert affiché)")
    print("  → Q : terminer\n")

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        found, corners = cv2.findChessboardCorners(gray, CHECKERBOARD, None)

        display = frame.copy()
        count = len(objpoints)

        if found:
            corners_refined = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
            cv2.drawChessboardCorners(display, CHECKERBOARD, corners_refined, found)
            cv2.putText(display, f"DETECTE — ESPACE pour capturer ({count}/{target})",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        else:
            cv2.putText(display, f"Cherche le damier... ({count}/{target})",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 100, 255), 2)

        cv2.imshow(f"Calibration distorsion - Cam {camera_index}", display)
        key = cv2.waitKey(1) & 0xFF

        if key == 32 and found:
            objpoints.append(objp)
            imgpoints.append(corners_refined)
            img_shape = gray.shape[::-1]
            print(f"  ✓ Capture {count + 1}/{target}")
            if count + 1 >= target:
                print("  Objectif atteint, vous pouvez continuer ou appuyer Q")
        elif key == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()

    return objpoints, imgpoints, img_shape


def calibrate_camera(camera_index: int, output_dir: Path, target_captures: int = 15) -> dict:
    """
    Lance la calibration interactive et sauvegarde les coefficients.
    Retourne les paramètres de calibration.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    objpoints, imgpoints, img_shape = collect_calibration_frames(camera_index, target_captures)

    if len(objpoints) < MIN_CAPTURES:
        raise ValueError(f"Pas assez de captures ({len(objpoints)}/{MIN_CAPTURES} minimum)")

    error, K, D, rvecs, tvecs = cv2.calibrateCamera(objpoints, imgpoints, img_shape, None, None)

    if error > MAX_REPROJ_ERROR:
        logger.warning(f"Erreur de reprojection élevée : {error:.3f}px (> {MAX_REPROJ_ERROR})")
    else:
        logger.info(f"Calibration OK — erreur reprojection : {error:.3f}px")

    result = {
        "camera_index": camera_index,
        "image_size": list(img_shape),
        "reprojection_error": round(float(error), 4),
        "camera_matrix": K.tolist(),
        "dist_coefficients": D.tolist(),
        "captures_used": len(objpoints),
    }

    output_path = output_dir / f"lens_cam{camera_index}.json"
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\n  Sauvegardé : {output_path}")
    print(f"  Erreur de reprojection : {error:.3f}px ", end="")
    print("✓ Excellent" if error < 0.5 else "✓ Bon" if error < 1.0 else "⚠ Refaire")

    return result


def load_lens_calibration(camera_index: int, data_dir: Path) -> tuple[np.ndarray, np.ndarray]:
    """Charge la calibration depuis le JSON. Retourne (camera_matrix, dist_coefficients)."""
    path = Path(data_dir) / f"lens_cam{camera_index}.json"
    if not path.exists():
        raise FileNotFoundError(f"Calibration distorsion manquante : {path}")

    with open(path) as f:
        data = json.load(f)

    K = np.array(data["camera_matrix"])
    D = np.array(data["dist_coefficients"])
    return K, D


def undistort(frame: np.ndarray, K: np.ndarray, D: np.ndarray) -> np.ndarray:
    """Corrige la distorsion d'une frame."""
    return cv2.undistort(frame, K, D)
