"""
Conversion d'une position (x, y) dans l'espace normalisé 800×800 → score dartboard.
Normes BDO/WDF/PDC.
"""

import math
from dataclasses import dataclass

CENTER = (400.0, 400.0)
REFERENCE_ANGLE_DEG = 81.0   # Rotation pour aligner le 20 à 12h

# Rayons en pixels dans l'espace normalisé 800×800
RING_RADII = [
    14,    # 0 — Bull's eye (Double bull)
    32,    # 1 — Outer bull (Single bull)
    194,   # 2 — Limite inner single / treble
    214,   # 3 — Limite treble / outer single
    320,   # 4 — Limite outer single / double
    340,   # 5 — Limite double / miss
]

# Secteurs dans le sens horaire depuis 12h (le 20 est en haut)
SECTORS = [20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5]
SECTOR_ANGLE = 360.0 / len(SECTORS)   # 18° par secteur


@dataclass
class DartScore:
    base: int           # Valeur du secteur (1–20, 25)
    multiplier: int     # 1 = single, 2 = double, 3 = treble
    score: int          # base × multiplier
    label: str          # "T20", "D5", "S7", "BULL", "DBULL", "MISS"
    angle_deg: float    # Angle calculé (debug)
    magnitude: float    # Distance au centre (debug)
    x: float            # Position normalisée
    y: float


def position_to_score(x: float, y: float) -> DartScore:
    """
    Convertit une position dans l'espace normalisé → score.
    x, y : coordonnées dans l'image 800×800
    """
    cx, cy = CENTER

    # Vecteur depuis le centre (axe Y inversé pour coordonnées mathématiques)
    vx = x - cx
    vy = cy - y

    magnitude = math.sqrt(vx * vx + vy * vy)

    # Calcul de l'angle, normalisé avec référence à 12h = secteur 20
    angle_raw = math.degrees(math.atan2(vy, vx))
    angle = math.fmod((angle_raw + 360.0 - REFERENCE_ANGLE_DEG), 360.0)

    # Détermination de l'anneau
    ring = _get_ring(magnitude)

    # Bull
    if ring == 0:
        return DartScore(base=25, multiplier=2, score=50, label="DBULL",
                         angle_deg=angle, magnitude=magnitude, x=x, y=y)
    if ring == 1:
        return DartScore(base=25, multiplier=1, score=25, label="BULL",
                         angle_deg=angle, magnitude=magnitude, x=x, y=y)

    # Miss
    if ring == -1:
        return DartScore(base=0, multiplier=0, score=0, label="MISS",
                         angle_deg=angle, magnitude=magnitude, x=x, y=y)

    # Secteur
    sector_idx = int(angle / SECTOR_ANGLE) % len(SECTORS)
    base = SECTORS[sector_idx]

    if ring == 2:    # Inner single
        mult, prefix = 1, "S"
    elif ring == 3:  # Treble
        mult, prefix = 3, "T"
    elif ring == 4:  # Outer single
        mult, prefix = 1, "S"
    else:            # ring == 5 → Double
        mult, prefix = 2, "D"

    label = f"{prefix}{base}"
    return DartScore(base=base, multiplier=mult, score=base * mult, label=label,
                     angle_deg=angle, magnitude=magnitude, x=x, y=y)


def _get_ring(magnitude: float) -> int:
    """
    Retourne l'index de l'anneau :
    0=bull, 1=outer bull, 2=inner single, 3=treble, 4=outer single, 5=double, -1=miss
    """
    for i, r in enumerate(RING_RADII):
        if magnitude <= r:
            return i
    return -1
