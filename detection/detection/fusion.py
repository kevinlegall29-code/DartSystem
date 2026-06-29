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

    # CONSENSUS INTER-CAMÉRAS sur les DEUX bouts de chaque fléchette.
    # La vraie pointe se projette au même endroit depuis toutes les caméras ;
    # les flights (hors plan) divergent. On choisit donc, pour chaque caméra,
    # le bout qui converge avec les autres → redondance robuste.
    AGREE_TOL = 75   # px

    # 2 candidats normalisés par caméra (pointe + flight, ordre incertain)
    cand = {}   # cam_idx -> [pt_norm, pt_norm]
    for cam_idx in cam_indices:
        loc = detections[cam_idx]
        ends = loc.corners[:2].reshape(-1, 1, 2).astype(np.float32)
        tr = cv2.perspectiveTransform(ends, homographies[cam_idx]).reshape(-1, 2)
        cand[cam_idx] = [tr[0], tr[1]]
        for k, p in enumerate(tr):
            s = position_to_score(float(p[0]), float(p[1]))
            logger.info(f"[CAM{cam_idx}] bout{k}=({p[0]:.0f},{p[1]:.0f}) → {s.label}")

    # Pour chaque candidat, cherche le bout le plus proche dans CHAQUE autre caméra.
    # Le meilleur groupe = celui avec le plus de caméras d'accord, puis le plus serré.
    best_group = None
    best_key = (0, 1e9)   # (nb caméras, -écart) → on maximise caméras puis minimise écart
    for ci in cam_indices:
        for pi in cand[ci]:
            group = [pi]
            cams_used = [ci]
            for cj in cam_indices:
                if cj == ci:
                    continue
                nearest = min(cand[cj], key=lambda q: np.linalg.norm(q - pi))
                if np.linalg.norm(nearest - pi) < AGREE_TOL:
                    group.append(nearest)
                    cams_used.append(cj)
            if len(cams_used) >= 2:
                spread = max(np.linalg.norm(a - b) for a in group for b in group)
                key = (len(cams_used), -spread)
                if key > best_key:
                    best_key = key
                    best_group = (np.mean(group, axis=0), cams_used)

    if best_group is not None:
        final, used = best_group
        confidence = 0.9
        agreement = True
    else:
        # Aucun accord : fallback sur le bout fin (pointe) de la plus longue vue
        best_cam = max(cam_indices, key=lambda c: dict(zip(cam_indices, [l[2] for l in lines]))[c])
        final = cand[best_cam][0]
        used = [best_cam]
        confidence = 0.5
        agreement = False

    x_final, y_final = float(final[0]), float(final[1])
    score = position_to_score(x_final, y_final)
    logger.info(f"FUSION cams {used} (accord={agreement}) → "
                f"({x_final:.0f},{y_final:.0f}) = {score.label}")

    return FusedDartResult(
        score=score, x_normalized=x_final, y_normalized=y_final,
        cameras_used=used, confidence=confidence, agreement=agreement,
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
