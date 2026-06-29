"""
Localisation de la fléchette par composantes connexes.
On isole le plus gros blob allongé (la fléchette), puis on prend ses 2 extrémités.
Évite de connecter la fléchette à du bruit lointain.
"""

import cv2
import numpy as np
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MIN_AREA = 80            # Surface minimale du blob fléchette
MIN_LENGTH = 30          # Longueur minimale entre extrémités


@dataclass
class DartLocation:
    corners: np.ndarray  # Shape (2, 2) : les 2 extrémités
    confidence: float
    corners_count: int

    @property
    def x(self) -> float:
        return float(self.corners[:, 0].mean())

    @property
    def y(self) -> float:
        return float(self.corners[:, 1].mean())


def detect_dart_location(diff_frame: np.ndarray, camera_side: str = "") -> DartLocation | None:
    # Relie les morceaux proches de la fléchette
    kernel = np.ones((5, 5), np.uint8)
    closed = cv2.morphologyEx(diff_frame, cv2.MORPH_CLOSE, kernel, iterations=2)
    closed = cv2.dilate(closed, kernel, iterations=1)

    # Composantes connexes : isole les blobs séparés
    num, labels, stats, _ = cv2.connectedComponentsWithStats(closed, connectivity=8)
    if num <= 1:
        return None

    # Choisit le blob le plus "fléchette" : grand ET allongé
    best_label = -1
    best_score = 0.0
    for lbl in range(1, num):
        area = stats[lbl, cv2.CC_STAT_AREA]
        if area < MIN_AREA:
            continue
        w = stats[lbl, cv2.CC_STAT_WIDTH]
        h = stats[lbl, cv2.CC_STAT_HEIGHT]
        elong = max(w, h) / max(1, min(w, h))   # allongement
        score = area * elong
        if score > best_score:
            best_score = score
            best_label = lbl

    if best_label < 0:
        return None

    # Pixels du blob fléchette uniquement
    ys, xs = np.nonzero(labels == best_label)
    pts = np.column_stack([xs, ys]).astype(np.float32)
    if len(pts) < MIN_AREA:
        return None

    # 2 extrémités via l'enveloppe convexe du blob (isolé du bruit)
    hull = cv2.convexHull(pts).reshape(-1, 2)
    max_dist = 0.0
    end1, end2 = hull[0], hull[0]
    for i in range(len(hull)):
        for j in range(i + 1, len(hull)):
            d = np.linalg.norm(hull[i] - hull[j])
            if d > max_dist:
                max_dist = d
                end1, end2 = hull[i], hull[j]

    if max_dist < MIN_LENGTH:
        return None

    corners = np.array([end1, end2], dtype=float)
    confidence = min(1.0, len(pts) / 2000.0)
    return DartLocation(corners=corners, confidence=confidence, corners_count=len(pts))
