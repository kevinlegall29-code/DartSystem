"""
Localisation de la fléchette par Harris corner detection sur la diff d'image.
"""

import cv2
import numpy as np
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Distance maximale au centre du cluster de corners (filtre outliers)
MAX_CLUSTER_SPREAD = 180
# Distance maximale d'un corner à la droite ajustée (filtre bruit)
MAX_LINE_DISTANCE = 40
# Nombre minimum de voisins pour valider un point de localisation
MIN_NEIGHBORS = 3
NEIGHBOR_RADIUS = 40


@dataclass
class DartLocation:
    """Position brute de la fléchette dans l'image caméra (coordonnées pixels)."""
    x: float
    y: float
    confidence: float   # 0.0 – 1.0 basé sur le nombre de corners cohérents
    corners_count: int


def detect_dart_location(diff_frame: np.ndarray, camera_side: str = "left") -> DartLocation | None:
    """
    Localise la fléchette dans une image de différence.

    diff_frame   : image binaire (résultat de absdiff + threshold)
    camera_side  : "left" | "right" | "top" selon la position de la caméra
    Retourne DartLocation ou None si non détecté.
    """
    corners = _get_harris_corners(diff_frame)
    if corners is None or len(corners) < 5:
        logger.debug("Pas assez de corners détectés")
        return None

    corners = _filter_outliers(corners)
    if corners is None or len(corners) < 3:
        logger.debug("Pas assez de corners après filtrage outliers")
        return None

    corners = _filter_by_line(corners, diff_frame.shape)
    if corners is None or len(corners) < 2:
        logger.debug("Pas assez de corners après filtrage ligne")
        return None

    location = _find_tip(corners, camera_side)
    if location is None:
        return None

    neighbors = _count_neighbors(location, corners)
    if neighbors < MIN_NEIGHBORS:
        logger.debug(f"Point isolé ({neighbors} voisins < {MIN_NEIGHBORS})")
        # Essaie le deuxième candidat
        location = _find_tip_fallback(corners, camera_side, location)
        if location is None:
            return None

    confidence = min(1.0, len(corners) / 50.0)
    return DartLocation(x=float(location[0]), y=float(location[1]),
                        confidence=confidence, corners_count=len(corners))


def _get_harris_corners(diff_frame: np.ndarray) -> np.ndarray | None:
    corners = cv2.goodFeaturesToTrack(
        diff_frame,
        maxCorners=640,
        qualityLevel=0.0008,
        minDistance=1,
        blockSize=3,
        useHarrisDetector=True,
        k=0.06,
    )
    return corners


def _filter_outliers(corners: np.ndarray) -> np.ndarray | None:
    pts = corners.reshape(-1, 2)
    mean = pts.mean(axis=0)
    mask = (np.abs(pts[:, 0] - mean[0]) < MAX_CLUSTER_SPREAD) & \
           (np.abs(pts[:, 1] - mean[1]) < MAX_CLUSTER_SPREAD * 0.67)
    filtered = pts[mask]
    return filtered if len(filtered) > 0 else None


def _filter_by_line(corners: np.ndarray, shape: tuple) -> np.ndarray | None:
    if len(corners) < 2:
        return corners

    pts = corners.reshape(-1, 1, 2).astype(np.float32)
    line = cv2.fitLine(pts, cv2.DIST_HUBER, 0, 0.01, 0.01).flatten()
    vx, vy, x0, y0 = float(line[0]), float(line[1]), float(line[2]), float(line[3])

    h, w = shape[:2]
    p1 = np.array([0.0, y0 + (-x0) * (vy / vx) if vx != 0 else y0])
    p2 = np.array([float(w), y0 + (w - x0) * (vy / vx) if vx != 0 else y0])

    def point_to_line_dist(p):
        ap = p - p1
        ab = p2 - p1
        t = np.dot(ap, ab) / (np.dot(ab, ab) + 1e-9)
        t = np.clip(t, 0, 1)
        proj = p1 + t * ab
        return np.linalg.norm(p - proj)

    pts_2d = corners.reshape(-1, 2).astype(float)
    mask = np.array([point_to_line_dist(p) < MAX_LINE_DISTANCE for p in pts_2d])
    filtered = pts_2d[mask]
    return filtered if len(filtered) > 0 else None


def _find_tip(corners: np.ndarray, camera_side: str) -> np.ndarray | None:
    """
    La pointe est le point du cluster de corners LE PLUS PROCHE du centre du board
    dans l'image caméra (la pointe est enfoncée dans la cible, le fût s'éloigne).
    Le centre approximatif de la cible dans l'image = centre de l'image caméra.
    """
    pts = corners.reshape(-1, 2).astype(float)
    board_center = np.array([640.0, 360.0])  # Centre approx pour 1280x720

    distances = np.linalg.norm(pts - board_center, axis=1)
    # Moyenne des 20% de points les plus proches du centre = zone de la pointe
    n = max(1, len(distances) // 5)
    closest_idx = np.argsort(distances)[:n]
    tip = pts[closest_idx].mean(axis=0)
    return tip


def _count_neighbors(point: np.ndarray, corners: np.ndarray) -> int:
    pts = corners.reshape(-1, 2)
    distances = np.abs(pts[:, 0] - point[0]) + np.abs(pts[:, 1] - point[1])
    return int(np.sum(distances < NEIGHBOR_RADIUS))
