"""
Localisation de la fléchette par RANSAC.
La fléchette est souvent COUPÉE en morceaux (les parties sombres se fondent dans
les segments noirs du board). Mais tous les morceaux sont ALIGNÉS sur l'axe de la
fléchette. RANSAC trouve la ligne qui relie le plus de morceaux à travers les trous,
et ignore le bruit hors-axe.
"""

import cv2
import numpy as np
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MIN_PIXELS = 60          # Pixels de différence minimum
MIN_LENGTH = 30          # Longueur minimale de la fléchette reconstruite
INLIER_DIST = 9          # Distance max (px) d'un pixel à la ligne pour être inlier
RANSAC_ITERS = 80


@dataclass
class DartLocation:
    corners: np.ndarray  # Shape (2, 2) : les 2 extrémités de la ligne reconstruite
    confidence: float
    corners_count: int

    @property
    def x(self) -> float:
        return float(self.corners[:, 0].mean())

    @property
    def y(self) -> float:
        return float(self.corners[:, 1].mean())


def detect_dart_location(diff_frame: np.ndarray, camera_side: str = "") -> DartLocation | None:
    # Nettoyage léger : retire le bruit isolé sans fermer les fragments
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(diff_frame, cv2.MORPH_OPEN, kernel)

    ys, xs = np.nonzero(mask)
    if len(xs) < MIN_PIXELS:
        return None

    pts = np.column_stack([xs, ys]).astype(np.float32)
    n = len(pts)
    rng = np.random.default_rng(42)

    best_count = 0
    best_dir = None
    best_p = None
    best_inliers = None

    for _ in range(RANSAC_ITERS):
        i, j = rng.choice(n, 2, replace=False)
        p1, p2 = pts[i], pts[j]
        d = p2 - p1
        norm = np.linalg.norm(d)
        if norm < 25:          # les 2 points doivent être assez écartés
            continue
        d = d / norm
        normal = np.array([-d[1], d[0]])
        dist = np.abs((pts - p1) @ normal)   # distance perpendiculaire à la ligne
        inliers = dist < INLIER_DIST
        count = int(inliers.sum())
        if count > best_count:
            best_count = count
            best_dir = d
            best_p = p1
            best_inliers = inliers

    if best_inliers is None or best_count < MIN_PIXELS * 0.5:
        return None

    # Reconstruit la fléchette : extrémités des inliers projetés sur la ligne
    inlier_pts = pts[best_inliers]
    ts = (inlier_pts - best_p) @ best_dir
    end1 = inlier_pts[int(np.argmin(ts))]
    end2 = inlier_pts[int(np.argmax(ts))]

    length = float(np.linalg.norm(end2 - end1))
    if length < MIN_LENGTH:
        return None

    corners = np.array([end1, end2], dtype=float)
    confidence = min(1.0, best_count / 1500.0)
    return DartLocation(corners=corners, confidence=confidence, corners_count=best_count)
