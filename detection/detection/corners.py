"""
Localisation de la fléchette par RANSAC + discrimination pointe/flight.

1. RANSAC trouve l'axe de la fléchette (relie les fragments coupés par les
   segments noirs, ignore le bruit hors-axe).
2. On garde le plus long segment CONTINU d'inliers (élimine le bruit lointain
   aligné par hasard).
3. La POINTE = le bout FIN (le fût), le FLIGHT = le bout LARGE (empennage).
   On mesure l'épaisseur perpendiculaire à chaque bout pour les distinguer.

corners[0] = pointe, corners[1] = flight.
"""

import cv2
import numpy as np
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MIN_PIXELS = 60
MIN_LENGTH = 30
INLIER_DIST = 9
RANSAC_ITERS = 80
GAP_MAX = 40        # trou max (px le long de l'axe) dans un segment continu


@dataclass
class DartLocation:
    corners: np.ndarray  # [pointe, flight] en espace caméra
    confidence: float
    corners_count: int

    @property
    def x(self) -> float:
        return float(self.corners[:, 0].mean())

    @property
    def y(self) -> float:
        return float(self.corners[:, 1].mean())


def detect_dart_location(diff_frame: np.ndarray, camera_side: str = "") -> DartLocation | None:
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(diff_frame, cv2.MORPH_OPEN, kernel)

    ys, xs = np.nonzero(mask)
    if len(xs) < MIN_PIXELS:
        return None

    pts = np.column_stack([xs, ys]).astype(np.float32)
    n = len(pts)
    rng = np.random.default_rng(42)

    best_count, best_dir, best_p, best_inliers = 0, None, None, None
    for _ in range(RANSAC_ITERS):
        i, j = rng.choice(n, 2, replace=False)
        d = pts[j] - pts[i]
        norm = np.linalg.norm(d)
        if norm < 25:
            continue
        d = d / norm
        normal = np.array([-d[1], d[0]])
        dist = np.abs((pts - pts[i]) @ normal)
        inliers = dist < INLIER_DIST
        count = int(inliers.sum())
        if count > best_count:
            best_count, best_dir, best_p, best_inliers = count, d, pts[i], inliers

    if best_inliers is None or best_count < MIN_PIXELS * 0.5:
        return None

    inlier_pts = pts[best_inliers]
    ts = (inlier_pts - best_p) @ best_dir
    ds = (inlier_pts - best_p) @ np.array([-best_dir[1], best_dir[0]])  # perpendiculaire

    # Garde le plus long segment CONTINU le long de l'axe (élimine bruit lointain)
    order = np.argsort(ts)
    ts_s = ts[order]
    seg_start = 0
    best_seg = (0, 0)
    for k in range(1, len(ts_s)):
        if ts_s[k] - ts_s[k - 1] > GAP_MAX:
            if ts_s[k - 1] - ts_s[seg_start] > ts_s[best_seg[1]] - ts_s[best_seg[0]]:
                best_seg = (seg_start, k - 1)
            seg_start = k
    if ts_s[-1] - ts_s[seg_start] > ts_s[best_seg[1]] - ts_s[best_seg[0]]:
        best_seg = (seg_start, len(ts_s) - 1)

    sel = order[best_seg[0]:best_seg[1] + 1]
    seg_pts = inlier_pts[sel]
    seg_ts = ts[sel]
    seg_ds = ds[sel]

    t_min, t_max = seg_ts.min(), seg_ts.max()
    length = float(t_max - t_min)
    if length < MIN_LENGTH:
        return None

    end_a = best_p + t_min * best_dir
    end_b = best_p + t_max * best_dir

    # Épaisseur à chaque bout : std de la distance perpendiculaire sur 30% du bout
    span = t_max - t_min
    near_a = seg_ds[seg_ts < t_min + 0.3 * span]
    near_b = seg_ds[seg_ts > t_max - 0.3 * span]
    width_a = float(np.std(near_a)) if len(near_a) > 2 else 0.0
    width_b = float(np.std(near_b)) if len(near_b) > 2 else 0.0

    # La pointe = le bout le plus FIN (épaisseur la plus faible)
    if width_a <= width_b:
        tip, flight = end_a, end_b
    else:
        tip, flight = end_b, end_a

    corners = np.array([tip, flight], dtype=float)
    confidence = min(1.0, len(seg_pts) / 1200.0)
    return DartLocation(corners=corners, confidence=confidence, corners_count=len(seg_pts))
