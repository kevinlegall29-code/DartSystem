"""
Fusion des détections des 3 caméras pour obtenir la position finale.
Stratégie : vote pondéré par la confiance + validation de cohérence.
"""

import cv2
import numpy as np
import logging
from dataclasses import dataclass

from detection.detection.corners import DartLocation
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


BOARD_CENTER_NORM = np.array([400.0, 400.0])


def find_tip_normalized(location: DartLocation, homography: np.ndarray) -> tuple[float, float] | None:
    """
    Transforme TOUS les corners en espace normalisé et retourne la pointe :
    le point le plus proche du centre du board (400, 400).
    La pointe est enfoncée dans le board = la plus proche du centre en espace normalisé.
    """
    pts = location.corners.reshape(-1, 1, 2).astype(np.float32)
    transformed = cv2.perspectiveTransform(pts, homography)
    pts_norm = transformed.reshape(-1, 2)

    # Filtre les points en dehors du board (magnitude > 380px)
    distances = np.linalg.norm(pts_norm - BOARD_CENTER_NORM, axis=1)
    valid = distances < 380
    if not valid.any():
        # Aucun point dans le board — prend quand même le plus proche
        pass
    else:
        pts_norm = pts_norm[valid]
        distances = distances[valid]

    # Moyenne des 20% de corners les plus proches du centre = zone de la pointe
    n = max(1, len(distances) // 5)
    tip_idx = np.argsort(distances)[:n]
    tip = pts_norm[tip_idx].mean(axis=0)
    return float(tip[0]), float(tip[1])


def fuse_detections(
    detections: dict[int, DartLocation | None],
    homographies: dict[int, np.ndarray],
) -> FusedDartResult | None:
    """
    Fusionne les détections de plusieurs caméras.

    detections   : {camera_index: DartLocation | None}
    homographies : {camera_index: np.ndarray 3×3}
    """
    # Transforme chaque détection valide en espace normalisé
    normalized: dict[int, tuple[float, float]] = {}
    confidences: dict[int, float] = {}

    for cam_idx, loc in detections.items():
        if loc is None or loc.confidence < MIN_CONFIDENCE:
            continue
        if cam_idx not in homographies:
            continue
        try:
            result = find_tip_normalized(loc, homographies[cam_idx])
            if result is None:
                continue
            x_n, y_n = result
            if 0 <= x_n <= 800 and 0 <= y_n <= 800:
                normalized[cam_idx] = (x_n, y_n)
                confidences[cam_idx] = loc.confidence
                # Debug : score par caméra
                from detection.scoring.board_mapping import position_to_score
                s = position_to_score(x_n, y_n)
                logger.info(f"[CAM{cam_idx}] tip=({x_n:.0f},{y_n:.0f}) → {s.label}")
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

    xs = np.array([p[0] for p in positions])
    ys = np.array([p[1] for p in positions])

    if agreement:
        weights = np.array(confs) / np.sum(confs)
        x_final = float(np.dot(weights, xs))
        y_final = float(np.dot(weights, ys))
        global_conf = float(np.mean(confs))
    else:
        # Désaccord : cherche une majorité 2/3 par secteur
        from detection.scoring.board_mapping import position_to_score
        from collections import Counter
        labels = [position_to_score(p[0], p[1]).label for p in positions]
        most_common, count = Counter(labels).most_common(1)[0]

        if count >= 2:
            # 2 caméras d'accord → utilise leur moyenne
            agree_idx = [i for i, l in enumerate(labels) if l == most_common]
            x_final = float(np.mean([positions[i][0] for i in agree_idx]))
            y_final = float(np.mean([positions[i][1] for i in agree_idx]))
            global_conf = float(np.mean([confs[i] for i in agree_idx]))
            logger.info(f"Majorité 2/3 : {most_common} (cams {[cam_indices[i] for i in agree_idx]})")
        else:
            # Aucune majorité → médiane
            x_final = float(np.median(xs))
            y_final = float(np.median(ys))
            global_conf = float(np.mean(confs)) * 0.6
            logger.warning(f"Désaccord total — médiane ({x_final:.0f},{y_final:.0f})")

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
