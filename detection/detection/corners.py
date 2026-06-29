"""
Localisation de la fléchette par analyse de contour sur la diff d'image.
Approche : contour principal → rectangle orienté minimum → deux extrémités.
Plus robuste que Harris corners car travaille sur la silhouette complète.
"""

import cv2
import numpy as np
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MIN_DART_AREA = 200      # Surface minimum du contour (pixels²)
MAX_DART_AREA = 50000    # Surface maximum
MIN_ASPECT_RATIO = 1.5  # La fléchette est allongée (longueur / largeur > 1.5)


@dataclass
class DartLocation:
    """Deux extrémités de la fléchette en espace caméra."""
    corners: np.ndarray  # Shape (2, 2) — les deux bouts de la fléchette
    confidence: float
    corners_count: int   # Nombre de pixels du contour

    @property
    def x(self) -> float:
        return float(self.corners[:, 0].mean())

    @property
    def y(self) -> float:
        return float(self.corners[:, 1].mean())


def detect_dart_location(diff_frame: np.ndarray, camera_side: str = "") -> DartLocation | None:
    """
    Détecte la fléchette dans l'image de différence.
    Retourne les deux extrémités de la fléchette (pointe et fût).
    """
    # Nettoie le masque : ferme les trous, garde la plus grande composante
    kernel = np.ones((3, 3), np.uint8)
    closed = cv2.morphologyEx(diff_frame, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return None

    valid = [c for c in contours if MIN_DART_AREA < cv2.contourArea(c) < MAX_DART_AREA]
    if not valid:
        return None

    # Garde le plus gros contour (la fléchette = plus gros changement cohérent)
    main = max(valid, key=cv2.contourArea)
    pts_contour = main.reshape(-1, 2).astype(np.float32)

    # fitLine robuste (Huber) → direction stable de l'axe de la fléchette
    line = cv2.fitLine(pts_contour, cv2.DIST_HUBER, 0, 0.01, 0.01).flatten()
    vx, vy, x0, y0 = float(line[0]), float(line[1]), float(line[2]), float(line[3])

    # Projette tous les points du contour sur la ligne → extrémités
    direction = np.array([vx, vy])
    origin = np.array([x0, y0])
    ts = (pts_contour - origin) @ direction
    t_min, t_max = float(ts.min()), float(ts.max())

    end1 = origin + t_min * direction
    end2 = origin + t_max * direction

    length = t_max - t_min
    if length < 10:   # Trop court pour une direction fiable
        return None

    pts = np.array([end1, end2], dtype=float)
    area = cv2.contourArea(main)
    confidence = min(1.0, area / 3000.0)

    return DartLocation(corners=pts, confidence=confidence, corners_count=int(area))
