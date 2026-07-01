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
    """
    if len(lines) < 2:
        return None
    A = np.zeros((2, 2))
    b = np.zeros(2)
    for p, d, w in lines:
        M = (np.eye(2) - np.outer(d, d)) * w
        A += M
        b += M @ p
    try:
        return np.linalg.solve(A, b)
    except np.linalg.LinAlgError:
        return None


def _line_point_dist(line, pt) -> float:
    """Distance perpendiculaire d'un point à une ligne (point, direction)."""
    p, d = line[0], line[1]
    v = np.asarray(pt) - p
    return float(abs(v[0] * d[1] - v[1] * d[0]))   # composante perpendiculaire


def _ransac_intersection(lines: list, tol: float = 25.0):
    """
    Intersection robuste : teste chaque paire de lignes, garde l'intersection
    soutenue par le plus de lignes (rejette la caméra défaillante).
    lines : liste de (point, direction, longueur). Retourne (point, indices_inliers).
    """
    n = len(lines)
    if n < 2:
        return None, []
    best_pt, best_inliers = None, []
    for i in range(n):
        for j in range(i + 1, n):
            pt = _intersect_lines([(lines[i][0], lines[i][1], 1.0),
                                   (lines[j][0], lines[j][1], 1.0)])
            if pt is None:
                continue
            inliers = [k for k in range(n) if _line_point_dist(lines[k], pt) < tol]
            if len(inliers) > len(best_inliers):
                best_inliers = inliers
                best_pt = pt
    if best_pt is None:
        return None, []
    # Raffine avec toutes les lignes inliers (pondérées par longueur²)
    refined = _intersect_lines([(lines[k][0], lines[k][1], lines[k][2] ** 2) for k in best_inliers])
    return (refined if refined is not None else best_pt), best_inliers


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

    # Longueur de ligne = fiabilité : une flèche vue de profil (ligne longue) situe
    # mieux la pointe qu'une flèche vue de bout (caméra du dessus, ligne courte).
    lengths = dict(zip(cam_indices, [l[2] for l in lines]))

    # CONSENSUS INTER-CAMÉRAS + REJET D'OUTLIER.
    # Chaque caméra propose ses 2 bouts. La vraie pointe se projette au même
    # endroit depuis toutes les caméras (les flights divergent). On cherche la
    # grappe la plus serrée (1 point par caméra), on rejette les outliers, on moyenne.
    AGREE_TOL = 50   # px — resserré : les pointes vraies s'accordent à ~30px
    ON_BOARD = 480   # accepte jusqu'au surround (MISS) ; au-delà = aberrant

    def on_board(p):
        return np.linalg.norm(np.asarray(p) - BOARD_CENTER_NORM) < ON_BOARD

    # 2 candidats normalisés par caméra (pointe + flight, ordre incertain)
    cand = {}   # cam_idx -> [pt_norm, ...] (on-board uniquement)
    for cam_idx in cam_indices:
        loc = detections[cam_idx]
        ends = loc.corners[:2].reshape(-1, 1, 2).astype(np.float32)
        tr = cv2.perspectiveTransform(ends, homographies[cam_idx]).reshape(-1, 2)
        cand[cam_idx] = [p for p in tr if on_board(p)]
        for k, p in enumerate(tr):
            s = position_to_score(float(p[0]), float(p[1]))
            logger.info(f"[CAM{cam_idx}] bout{k}=({p[0]:.0f},{p[1]:.0f}) → {s.label}")

    # Pour chaque candidat-ancre, rassemble le bout le plus proche de CHAQUE autre
    # caméra (< TOL), rejette les outliers vs la médiane, garde la meilleure grappe.
    best = None
    best_key = (0, 1e9)
    for ci in cam_indices:
        for pi in cand[ci]:
            group = {ci: pi}
            for cj in cam_indices:
                if cj == ci or not cand[cj]:
                    continue
                nearest = min(cand[cj], key=lambda q: np.linalg.norm(q - pi))
                if np.linalg.norm(nearest - pi) < AGREE_TOL:
                    group[cj] = nearest
            if len(group) >= 2:
                pts = np.array(list(group.values()))
                med = np.median(pts, axis=0)
                # rejet d'outlier : ne garde que les caméras proches de la médiane
                inliers = {c: p for c, p in group.items()
                           if np.linalg.norm(p - med) < AGREE_TOL}
                if len(inliers) >= 2:
                    inlier_cams = list(inliers.keys())
                    ipts = np.array([inliers[c] for c in inlier_cams])
                    spread = float(max(np.linalg.norm(a - b) for a in ipts for b in ipts))
                    key = (len(inliers), -spread)
                    if key > best_key:
                        best_key = key
                        # Moyenne PONDÉRÉE par la longueur de ligne² (fiabilité) :
                        # la caméra du dessus (ligne courte) pèse moins.
                        w = np.array([max(lengths[c], 1.0) ** 2 for c in inlier_cams])
                        wmean = (ipts * w[:, None]).sum(axis=0) / w.sum()
                        best = (wmean, inlier_cams)

    if best is not None:
        # Consensus multi-caméras (le plus fiable)
        final, used = best
        confidence, agreement, method = 0.9, True, "consensus"
    else:
        # Aucun accord → meilleure caméra (ligne la plus longue), pointe = corners[0]
        onboard_cams = [c for c in cam_indices if cand[c]]
        if not onboard_cams:
            logger.info("FUSION : aucun point plausible dans le board")
            return None
        best_cam = max(onboard_cams, key=lambda c: lengths[c])
        final = cand[best_cam][0]   # corners[0] = pointe (vote densité/centroïde)
        used = [best_cam]
        confidence, agreement, method = 0.5, False, "mono-caméra"

    x_final, y_final = float(final[0]), float(final[1])
    score = position_to_score(x_final, y_final)
    logger.info(f"FUSION [{method}] cams {used} → ({x_final:.0f},{y_final:.0f}) = {score.label}")

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
