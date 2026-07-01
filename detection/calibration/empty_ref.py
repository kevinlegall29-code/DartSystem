"""
Référence "board vide" persistée par caméra.

Sert à deux choses :
1. Détecter si des fléchettes sont plantées (comparaison à la vue actuelle).
2. Éviter de capturer une référence de détection POLLUÉE (avec des fléchettes).

La comparaison normalise la luminosité → tolérante aux changements d'exposition.
"""

import cv2
import numpy as np
from pathlib import Path

# Pixels de différence (après normalisation) au-delà desquels on considère
# qu'il y a quelque chose sur le board (fléchette(s)).
DART_PRESENT_PX = 500


def _blur_gray(frame: np.ndarray) -> np.ndarray:
    """Gris + flou, identique à ce que le détecteur de mouvement utilise."""
    if frame.ndim == 3:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.GaussianBlur(frame, (5, 5), 0)


def save_empty_reference(cam_idx: int, frame: np.ndarray, data_dir: Path) -> np.ndarray:
    """Sauve le board vide (gris flou) de la caméra sur disque. Retourne le gris."""
    gray = _blur_gray(frame)
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    np.save(data_dir / f"empty_cam{cam_idx}.npy", gray)
    return gray


def load_empty_reference(cam_idx: int, data_dir: Path) -> np.ndarray | None:
    """Charge le board vide de référence, ou None s'il n'existe pas."""
    p = Path(data_dir) / f"empty_cam{cam_idx}.npy"
    if not p.exists():
        return None
    try:
        return np.load(p)
    except Exception:
        return None


def board_has_darts(current: np.ndarray, golden_gray: np.ndarray | None) -> tuple[bool, int]:
    """
    Compare la vue actuelle au board-vide de référence.
    Normalise la luminosité globale (l'exposition a pu changer depuis la sauvegarde),
    puis compte les pixels réellement différents (= fléchette(s) ajoutée(s)).

    Retourne (has_darts, nonzero_px).
    """
    if golden_gray is None:
        return False, 0
    cur = _blur_gray(current)
    if cur.shape != golden_gray.shape:
        return False, 0

    # Aligne la luminosité moyenne (robuste au changement d'expo)
    cf = cur.astype(np.float32)
    gf = golden_gray.astype(np.float32)
    ratio = gf.mean() / max(cf.mean(), 1.0)
    cf = np.clip(cf * ratio, 0, 255).astype(np.uint8)

    diff = cv2.absdiff(cf, golden_gray)
    _, th = cv2.threshold(diff, 35, 255, cv2.THRESH_BINARY)
    # Érosion forte : supprime les FINES lignes de désalignement (bords de secteurs
    # décalés de 1-2px) tout en gardant les FORMES ÉPAISSES (fléchettes).
    th = cv2.morphologyEx(th, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    # Ne compte que les gros blobs compacts (une fléchette est un objet de bonne
    # taille) — ignore les petits résidus dispersés dus au bruit/alignement.
    n, _, stats, _ = cv2.connectedComponentsWithStats(th, connectivity=8)
    dart_px = sum(int(stats[i, cv2.CC_STAT_AREA]) for i in range(1, n)
                  if stats[i, cv2.CC_STAT_AREA] > 200)
    return dart_px > DART_PRESENT_PX, dart_px
