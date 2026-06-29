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
    # Améliore le contraste de la diff
    kernel = np.ones((3, 3), np.uint8)
    dilated = cv2.dilate(diff_frame, kernel, iterations=2)
    closed  = cv2.morphologyEx(dilated, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    # Garde les contours de taille plausible pour une fléchette
    valid = [
        c for c in contours
        if MIN_DART_AREA < cv2.contourArea(c) < MAX_DART_AREA
    ]
    if not valid:
        return None

    # Fusionne tous les contours valides (la fléchette peut apparaître en plusieurs morceaux)
    all_pts = np.vstack(valid)

    # Rectangle orienté minimum autour de la fléchette
    rect = cv2.minAreaRect(all_pts)
    box  = cv2.boxPoints(rect)   # 4 coins du rectangle

    (cx, cy), (w, h), angle = rect
    long_side  = max(w, h)
    short_side = min(w, h)

    if short_side < 1 or long_side / short_side < MIN_ASPECT_RATIO:
        # Pas assez allongé → probablement pas une fléchette
        # On utilise quand même le centroïde comme fallback
        M = cv2.moments(all_pts)
        if M["m00"] == 0:
            return None
        cx_pt = M["m10"] / M["m00"]
        cy_pt = M["m01"] / M["m00"]
        pts = np.array([[cx_pt, cy_pt], [cx_pt, cy_pt]], dtype=float)
        return DartLocation(corners=pts, confidence=0.3, corners_count=len(all_pts))

    # Les deux extrémités du grand axe du rectangle orienté
    # box[0], box[1], box[2], box[3] = coins dans le sens horaire
    # Les extrémités du grand axe sont les paires de coins adjacents les plus éloignés
    if w >= h:
        # Le grand axe est horizontal dans le rectangle
        end1 = ((box[0] + box[3]) / 2)
        end2 = ((box[1] + box[2]) / 2)
    else:
        end1 = ((box[0] + box[1]) / 2)
        end2 = ((box[2] + box[3]) / 2)

    pts = np.array([end1, end2], dtype=float)
    area = cv2.contourArea(all_pts)
    confidence = min(1.0, area / 5000.0)

    return DartLocation(corners=pts, confidence=confidence, corners_count=int(area))
