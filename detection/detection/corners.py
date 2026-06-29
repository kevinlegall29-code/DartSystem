"""
Localisation de la fléchette : on cherche les DEUX POINTS LES PLUS ÉLOIGNÉS
de l'ensemble des pixels de différence = la vraie longueur de la fléchette
(de la pointe au bout du flight). Évite de se limiter au flight seul.
"""

import cv2
import numpy as np
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MIN_PIXELS = 80          # Pixels minimum pour une fléchette
MIN_LENGTH = 30          # Longueur minimale (px) entre les 2 extrémités


@dataclass
class DartLocation:
    """Deux extrémités de la fléchette en espace caméra : [pointe?, flight?]."""
    corners: np.ndarray  # Shape (2, 2)
    confidence: float
    corners_count: int

    @property
    def x(self) -> float:
        return float(self.corners[:, 0].mean())

    @property
    def y(self) -> float:
        return float(self.corners[:, 1].mean())


def detect_dart_location(diff_frame: np.ndarray, camera_side: str = "") -> DartLocation | None:
    """
    Trouve les 2 points les plus éloignés de la silhouette de la fléchette.
    Retourne ces 2 extrémités (l'orientation pointe/flight est résolue ensuite).
    """
    # Ferme les trous pour relier flight + fût en une silhouette continue
    kernel = np.ones((5, 5), np.uint8)
    closed = cv2.morphologyEx(diff_frame, cv2.MORPH_CLOSE, kernel, iterations=2)

    ys, xs = np.nonzero(closed)
    if len(xs) < MIN_PIXELS:
        return None

    pts = np.column_stack([xs, ys]).astype(np.float32)

    # Enveloppe convexe → les 2 points les plus éloignés sont forcément dessus
    try:
        hull = cv2.convexHull(pts).reshape(-1, 2)
    except cv2.error:
        return None

    if len(hull) < 2:
        return None

    # Diamètre de l'enveloppe = paire de points la plus éloignée
    max_dist = 0.0
    end1, end2 = hull[0], hull[1]
    for i in range(len(hull)):
        for j in range(i + 1, len(hull)):
            d = np.linalg.norm(hull[i] - hull[j])
            if d > max_dist:
                max_dist = d
                end1, end2 = hull[i], hull[j]

    if max_dist < MIN_LENGTH:
        return None

    corners = np.array([end1, end2], dtype=float)
    confidence = min(1.0, len(xs) / 2000.0)
    return DartLocation(corners=corners, confidence=confidence, corners_count=len(xs))
