"""
Outil de diagnostic visuel : sauvegarde des images annotées pour chaque
détection de fléchette, par caméra. Permet de voir EXACTEMENT ce que le
système détecte (contour, extrémités, pointe, position normalisée).
"""

import cv2
import numpy as np
from pathlib import Path

DEBUG_DIR = Path(__file__).parent.parent / "data" / "debug"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

# Rayons des anneaux dans l'espace normalisé (pour overlay scoring)
RING_RADII = [14, 32, 194, 214, 320, 340]


def save_camera_detection(
    cam_idx: int,
    raw_frame: np.ndarray,
    thresh: np.ndarray,
    endpoints: np.ndarray | None,
    tip_camera_space: np.ndarray | None,
):
    """
    Sauvegarde l'image caméra avec le contour détecté et les extrémités.
    - endpoints : les 2 bouts de la fléchette en espace caméra (Nx2)
    - tip_camera_space : l'extrémité choisie comme pointe (2,)
    """
    img = raw_frame.copy()

    # Overlay du masque de détection en rouge transparent
    mask_color = np.zeros_like(img)
    mask_color[thresh > 0] = (0, 0, 200)
    img = cv2.addWeighted(img, 1.0, mask_color, 0.4, 0)

    if endpoints is not None and len(endpoints) >= 2:
        for pt in endpoints:
            cv2.circle(img, (int(pt[0]), int(pt[1])), 8, (0, 165, 255), 2)
        # Trace la ligne de la fléchette PROLONGÉE (montre la direction d'intersection)
        p1 = np.array(endpoints[0], dtype=float)
        p2 = np.array(endpoints[1], dtype=float)
        d = p2 - p1
        n = np.linalg.norm(d)
        if n > 1:
            d = d / n
            far1 = p1 - d * 2000
            far2 = p2 + d * 2000
            cv2.line(img, (int(far1[0]), int(far1[1])),
                     (int(far2[0]), int(far2[1])), (255, 255, 0), 1)
            cv2.line(img, (int(p1[0]), int(p1[1])),
                     (int(p2[0]), int(p2[1])), (255, 200, 0), 3)

    if tip_camera_space is not None:
        cv2.circle(img, (int(tip_camera_space[0]), int(tip_camera_space[1])),
                   12, (0, 255, 0), 3)
        cv2.putText(img, "TIP", (int(tip_camera_space[0]) + 15, int(tip_camera_space[1])),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

    cv2.imwrite(str(DEBUG_DIR / f"cam{cam_idx}_detect.jpg"), img,
                [cv2.IMWRITE_JPEG_QUALITY, 80])


def save_normalized_view(
    cam_idx: int,
    raw_frame: np.ndarray,
    homography: np.ndarray,
    tip_normalized: tuple[float, float] | None,
    label: str = "",
    both_endpoints: np.ndarray | None = None,
    consensus: tuple[float, float] | None = None,
):
    """
    Vue normalisée 800x800 avec anneaux, les 2 extrémités transformées,
    la pointe choisie, et le point de consensus final.
    """
    warped = cv2.warpPerspective(raw_frame, homography, (800, 800))

    center = (400, 400)
    for r in RING_RADII:
        cv2.circle(warped, center, r, (0, 255, 255), 1)
    cv2.line(warped, (400, 0), (400, 800), (100, 100, 100), 1)
    cv2.line(warped, (0, 400), (800, 400), (100, 100, 100), 1)

    # Ligne-fléchette transformée + extrémités (magenta)
    if both_endpoints is not None and len(both_endpoints) >= 2:
        pts = both_endpoints.reshape(-1, 1, 2).astype(np.float32)
        tr = cv2.perspectiveTransform(pts, homography).reshape(-1, 2)
        for p in tr:
            cv2.circle(warped, (int(p[0]), int(p[1])), 7, (255, 0, 255), 2)
        # Trace la ligne prolongée (sa direction doit pointer vers la vraie pointe)
        d = tr[1] - tr[0]
        n = np.linalg.norm(d)
        if n > 1:
            d = d / n
            f1 = tr[0] - d * 1000
            f2 = tr[1] + d * 1000
            cv2.line(warped, (int(f1[0]), int(f1[1])),
                     (int(f2[0]), int(f2[1])), (255, 0, 255), 1)

    if tip_normalized is not None:
        tx, ty = int(tip_normalized[0]), int(tip_normalized[1])
        cv2.circle(warped, (tx, ty), 10, (0, 255, 0), 3)
        cv2.putText(warped, label, (tx + 15, ty),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)

    # Point de consensus final (rouge) — identique sur les 3 vues
    if consensus is not None:
        cx, cy = int(consensus[0]), int(consensus[1])
        cv2.drawMarker(warped, (cx, cy), (0, 0, 255), cv2.MARKER_CROSS, 30, 3)

    cv2.imwrite(str(DEBUG_DIR / f"cam{cam_idx}_norm.jpg"), warped,
                [cv2.IMWRITE_JPEG_QUALITY, 80])
