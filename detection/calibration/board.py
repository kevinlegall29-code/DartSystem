"""
Calibration de la cible : 4 points manuels → homographie → vue normalisée 800×800.
Les 4 points sont placés aux intersections des fils de secteur sur l'anneau double.
"""

import cv2
import numpy as np
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

OUTPUT_SIZE = 800       # Image normalisée 800×800 pixels
DOUBLE_RADIUS = 340     # Rayon du double ring dans l'espace normalisé (pixels)

# Positions destination des 4 points dans l'espace normalisé (800×800, centre=400)
# Intersections choisies : écartées à ~90° pour maximiser la précision homographique
CALIB_POINTS_DST: dict[str, tuple[float, float]] = {
    "20_1":  (400.0, 400.0 - DOUBLE_RADIUS),   # 12h (entre 20 et 1)
    "6_10":  (400.0 + DOUBLE_RADIUS, 400.0),   # 3h  (entre 6 et 10)
    "3_19":  (400.0, 400.0 + DOUBLE_RADIUS),   # 6h  (entre 3 et 19)
    "11_14": (400.0 - DOUBLE_RADIUS, 400.0),   # 9h  (entre 11 et 14)
}

# Rayons de référence dans l'espace normalisé (px), norme BDO
RING_RADII = {
    "bulls_eye":    14,
    "outer_bull":   32,
    "single_inner": 194,
    "treble_inner": 214,
    "single_outer": 320,
    "double_inner": 340,
}

# Ordre des secteurs dans le sens horaire, en partant de 12h (20)
SECTOR_ORDER = [20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5]


def compute_homography(src_points: dict[str, tuple[float, float]]) -> np.ndarray:
    """
    Calcule la matrice homographie 3×3 depuis les 4 points utilisateur.

    src_points : {"20_1": (x, y), "6_10": (x, y), "3_19": (x, y), "11_14": (x, y)}
                 Coordonnées dans l'image caméra brute (après undistort)
    """
    keys = list(CALIB_POINTS_DST.keys())
    src = np.float32([src_points[k] for k in keys])
    dst = np.float32([CALIB_POINTS_DST[k] for k in keys])
    H = cv2.getPerspectiveTransform(src, dst)
    return H


def normalize_frame(frame: np.ndarray, H: np.ndarray) -> np.ndarray:
    """Applique l'homographie pour obtenir la vue normalisée 800×800."""
    return cv2.warpPerspective(frame, H, (OUTPUT_SIZE, OUTPUT_SIZE))


def validate_calibration(normalized: np.ndarray) -> dict:
    """
    Détecte les anneaux par transformée de Hough circulaire sur la vue normalisée.
    Retourne un score de qualité et les anneaux détectés.
    """
    gray = cv2.cvtColor(normalized, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=20,
        param1=50,
        param2=30,
        minRadius=10,
        maxRadius=OUTPUT_SIZE // 2,
    )

    detected_rings = []
    quality_score = 0.0
    center_error = None

    if circles is not None:
        circles = np.round(circles[0]).astype(int)
        center = np.array([OUTPUT_SIZE // 2, OUTPUT_SIZE // 2])

        for x, y, r in circles:
            detected_rings.append({"x": int(x), "y": int(y), "r": int(r)})

        # Évalue la précision du centre
        centers = np.array([[c["x"], c["y"]] for c in detected_rings])
        mean_center = centers.mean(axis=0)
        center_error = float(np.linalg.norm(mean_center - center))

        # Score : 100 si centre parfait, pénalité de 1pt par pixel d'écart
        quality_score = max(0.0, 100.0 - center_error)

    return {
        "quality_score": round(quality_score, 1),
        "center_error_px": round(center_error, 1) if center_error is not None else None,
        "detected_rings": detected_rings,
        "rings_count": len(detected_rings),
    }


def save_board_calibration(
    camera_index: int,
    src_points: dict,
    H: np.ndarray,
    validation: dict,
    output_dir: Path,
) -> Path:
    data = {
        "camera_index": camera_index,
        "src_points": src_points,
        "homography": H.tolist(),
        "ring_radii": RING_RADII,
        "validation": validation,
    }
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"board_cam{camera_index}.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    logger.info(f"Calibration board cam{camera_index} sauvegardée → {path}")
    return path


def load_board_calibration(camera_index: int, data_dir: Path) -> dict:
    path = Path(data_dir) / f"board_cam{camera_index}.json"
    if not path.exists():
        raise FileNotFoundError(f"Calibration board manquante : {path}")
    with open(path) as f:
        data = json.load(f)
    data["homography"] = np.array(data["homography"])
    return data
