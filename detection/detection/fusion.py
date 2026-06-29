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
    Trouve la pointe de la fléchette.

    Principe géométrique clé : l'homographie n'est valide QUE pour les points
    sur le plan du board. La pointe est plantée dans le board (sur le plan),
    le flight est au-dessus (hors plan → projection erronée).

    On choisit donc la pointe en espace CAMÉRA (la fléchette pointe vers le
    centre du board), puis on projette UNIQUEMENT ce point.
    """
    corners = location.corners.reshape(-1, 2).astype(np.float32)
    if len(corners) < 2:
        return None

    # Centre du board projeté en espace caméra (via homographie inverse)
    H_inv = np.linalg.inv(homography)
    center_cam = cv2.perspectiveTransform(
        np.array([[[400.0, 400.0]]], dtype=np.float32), H_inv
    )[0][0]

    # La pointe = l'extrémité la plus proche du centre du board EN ESPACE CAMÉRA
    # (la fléchette entre depuis la périphérie en pointant vers le centre)
    d0 = np.linalg.norm(corners[0] - center_cam)
    d1 = np.linalg.norm(corners[1] - center_cam)
    tip_cam = corners[0] if d0 <= d1 else corners[1]

    # Projette UNIQUEMENT la pointe (elle est sur le plan du board)
    tip_norm = cv2.perspectiveTransform(
        np.array([[tip_cam]], dtype=np.float32), homography
    )[0][0]

    return float(tip_norm[0]), float(tip_norm[1])


def _dart_line_normalized(location: DartLocation, homography: np.ndarray):
    """
    Transforme la ligne de la fléchette en espace normalisé.
    Retourne (point, direction_unitaire, longueur) ou None.
    La longueur en espace normalisé = fiabilité : une fléchette vue de profil
    donne une ligne longue (fiable), vue de bout un blob court (peu fiable).
    """
    corners = location.corners.reshape(-1, 2).astype(np.float32)
    if len(corners) < 2:
        return None
    pts = corners[:2].reshape(-1, 1, 2)
    tr = cv2.perspectiveTransform(pts, homography).reshape(-1, 2)
    p1, p2 = tr[0], tr[1]
    d = p2 - p1
    norm = np.linalg.norm(d)
    if norm < 1e-6:
        return None
    return p1, d / norm, float(norm)


def _intersect_lines(lines: list) -> np.ndarray | None:
    """
    Point minimisant la distance perpendiculaire pondérée aux lignes.
    lines : liste de (point, direction_unitaire, poids).
    Le poids (longueur de ligne) fait dominer les caméras voyant la fléchette de profil.
    """
    if len(lines) < 2:
        return None
    A = np.zeros((2, 2))
    b = np.zeros(2)
    for p, d, w in lines:
        M = (np.eye(2) - np.outer(d, d)) * w   # projecteur perpendiculaire pondéré
        A += M
        b += M @ p
    try:
        return np.linalg.solve(A, b)
    except np.linalg.LinAlgError:
        return None


def fuse_detections(
    detections: dict[int, DartLocation | None],
    homographies: dict[int, np.ndarray],
) -> FusedDartResult | None:
    """
    Fusionne les détections de plusieurs caméras.

    detections   : {camera_index: DartLocation | None}
    homographies : {camera_index: np.ndarray 3×3}
    """
    from detection.scoring.board_mapping import position_to_score

    # Collecte les lignes-fléchettes en espace normalisé
    lines = []
    cam_indices = []
    confs = []

    for cam_idx, loc in detections.items():
        if loc is None or loc.confidence < MIN_CONFIDENCE:
            continue
        if cam_idx not in homographies:
            continue
        line = _dart_line_normalized(loc, homographies[cam_idx])
        if line is None:
            continue
        lines.append(line)
        cam_indices.append(cam_idx)
        confs.append(loc.confidence)
        # Debug : longueur de ligne (fiabilité) par caméra
        logger.info(f"[CAM{cam_idx}] ligne longueur={line[2]:.0f}px (poids fiabilité)")

    if not lines:
        return None

    # MÉTHODE PRINCIPALE : intersection des lignes-fléchettes.
    # Chaque ligne (projetée sur le plan board) passe par la pointe physique,
    # peu importe où se trouve le flight. L'intersection = la pointe.
    if len(lines) >= 2:
        # Pondère par longueur² (vues de profil = directions fiables)
        weighted = [(p, d, length ** 2) for (p, d, length) in lines]
        tip = _intersect_lines(weighted)
        if tip is not None:
            mag = np.linalg.norm(tip - BOARD_CENTER_NORM)
            if mag < 420:
                x_final, y_final = float(tip[0]), float(tip[1])
                score = position_to_score(x_final, y_final)
                logger.info(f"INTERSECTION {len(lines)} lignes (cams {cam_indices}) → "
                            f"({x_final:.0f},{y_final:.0f}) = {score.label}")
                return FusedDartResult(
                    score=score, x_normalized=x_final, y_normalized=y_final,
                    cameras_used=cam_indices, confidence=float(np.mean(confs)),
                    agreement=True,
                )

    # FALLBACK : 1 seule ligne → pointe naïve de la meilleure caméra
    best_i = int(np.argmax([l[2] for l in lines]))
    best_cam = cam_indices[best_i]
    tip = find_tip_normalized(detections[best_cam], homographies[best_cam])
    if tip is None:
        return None
    score = position_to_score(*tip)
    logger.info(f"FALLBACK cam{best_cam} → ({tip[0]:.0f},{tip[1]:.0f}) = {score.label}")
    return FusedDartResult(
        score=score, x_normalized=tip[0], y_normalized=tip[1],
        cameras_used=[best_cam], confidence=confs[best_i] * 0.5, agreement=False,
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
