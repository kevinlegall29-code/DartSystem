"""
Fusion des détections des 3 caméras pour obtenir la position finale.
Stratégie : vote pondéré par la confiance + validation de cohérence.
"""

import numpy as np
import logging
from dataclasses import dataclass

from detection.corners import DartLocation
from detection.calibration.board import normalize_frame, CALIB_POINTS_DST
from detection.scoring.board_mapping import DartScore, position_to_score

logger = logging.getLogger(__name__)

# Tolérance d'accord entre caméras (en pixels dans l'espace normalisé)
AGREEMENT_TOLERANCE_PX = 30
# Confiance minimale pour qu'une caméra participe à la fusion
MIN_CONFIDENCE = 0.1


@dataclass
class FusedDartResult:
    score: DartScore
    x_normalized: float
    y_normalized: float
    cameras_used: list[int]         # Indices des caméras ayant contribué
    confidence: float               # Confiance globale 0–1
    agreement: bool                 # Les caméras étaient-elles cohérentes ?


def transform_to_normalized(location: DartLocation, homography: np.ndarray) -> tuple[float, float]:
    """Transforme une position brute caméra → espace normalisé 800×800."""
    pt = np.array([[[location.x, location.y]]], dtype=np.float32)
    transformed = cv2.perspectiveTransform(pt, homography)  # noqa: F821
    x, y = transformed[0][0]
    return float(x), float(y)


def fuse_detections(
    detections: dict[int, DartLocation | None],
    homographies: dict[int, np.ndarray],
) -> FusedDartResult | None:
    """
    Fusionne les détections de plusieurs caméras.

    detections   : {camera_index: DartLocation | None}
    homographies : {camera_index: np.ndarray 3×3}
    """
    import cv2

    # Transforme chaque détection valide en espace normalisé
    normalized: dict[int, tuple[float, float]] = {}
    confidences: dict[int, float] = {}

    for cam_idx, loc in detections.items():
        if loc is None or loc.confidence < MIN_CONFIDENCE:
            continue
        if cam_idx not in homographies:
            continue
        try:
            x_n, y_n = transform_to_normalized(loc, homographies[cam_idx])
            # Rejette les points hors de la zone valide
            if 0 <= x_n <= 800 and 0 <= y_n <= 800:
                normalized[cam_idx] = (x_n, y_n)
                confidences[cam_idx] = loc.confidence
        except Exception as e:
            logger.warning(f"Erreur transformation caméra {cam_idx}: {e}")

    if not normalized:
        logger.debug("Aucune détection valide à fusionner")
        return None

    if len(normalized) == 1:
        # Une seule caméra disponible
        cam_idx = next(iter(normalized))
        x, y = normalized[cam_idx]
        score = position_to_score(x, y)
        return FusedDartResult(
            score=score, x_normalized=x, y_normalized=y,
            cameras_used=[cam_idx], confidence=confidences[cam_idx], agreement=False
        )

    # Vérifie la cohérence entre caméras
    positions = list(normalized.values())
    cam_indices = list(normalized.keys())
    confs = [confidences[i] for i in cam_indices]

    agreement = _check_agreement(positions)

    if agreement:
        # Moyenne pondérée par la confiance
        weights = np.array(confs)
        weights /= weights.sum()
        xs = np.array([p[0] for p in positions])
        ys = np.array([p[1] for p in positions])
        x_final = float(np.dot(weights, xs))
        y_final = float(np.dot(weights, ys))
        global_conf = float(np.mean(confs))
    else:
        # Désaccord : prend la caméra avec la meilleure confiance
        best_idx = int(np.argmax(confs))
        x_final, y_final = positions[best_idx]
        global_conf = confs[best_idx] * 0.7  # Pénalité de confiance
        logger.warning(f"Désaccord caméras {cam_indices} — utilise cam {cam_indices[best_idx]}")

    score = position_to_score(x_final, y_final)
    return FusedDartResult(
        score=score,
        x_normalized=x_final,
        y_normalized=y_final,
        cameras_used=cam_indices,
        confidence=global_conf,
        agreement=agreement,
    )


def _check_agreement(positions: list[tuple[float, float]]) -> bool:
    """Vérifie si toutes les positions sont dans la tolérance."""
    if len(positions) < 2:
        return True
    pts = np.array(positions)
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            dist = np.linalg.norm(pts[i] - pts[j])
            if dist > AGREEMENT_TOLERANCE_PX:
                return False
    return True
