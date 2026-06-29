"""
Localisation de la fléchette par Harris corner detection sur la diff d'image.
Retourne les corners filtrés en espace caméra — la pointe est déterminée
APRÈS transformation homographique dans l'espace normalisé.
"""

import cv2
import numpy as np
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MAX_CLUSTER_SPREAD = 180
MAX_LINE_DISTANCE  = 40


@dataclass
class DartLocation:
    """Ensemble de corners filtrés en espace caméra."""
    corners: np.ndarray  # Nx2, coordonnées pixels caméra
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
    Localise la fléchette dans une image de différence.

    diff_frame   : image binaire (résultat de absdiff + threshold)
    camera_side  : "left" | "right" | "top" selon la position de la caméra
    Retourne DartLocation ou None si non détecté.
    """
    corners = _get_harris_corners(diff_frame)
    if corners is None or len(corners) < 5:
        return None

    corners = _filter_outliers(corners)
    if corners is None or len(corners) < 3:
        return None

    corners = _filter_by_line(corners, diff_frame.shape)
    if corners is None or len(corners) < 2:
        return None

    confidence = min(1.0, len(corners) / 50.0)
    return DartLocation(corners=corners.reshape(-1, 2).astype(float),
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




