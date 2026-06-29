"""
Détection de mouvement par différence d'image.
Déclenche la phase d'analyse quand une fléchette est détectée (frame stable après lancer).
"""

import cv2
import numpy as np
import time
import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class MotionState(Enum):
    IDLE = "idle"               # Pas de mouvement
    MOTION_DETECTED = "motion"  # Mouvement en cours (fléchette en vol)
    DART_STABLE = "stable"      # Fléchette plantée, prête à analyser
    TAKEOUT = "takeout"         # Retrait des fléchettes (grand mouvement)


@dataclass
class MotionResult:
    state: MotionState
    diff_frame: np.ndarray | None = None
    nonzero_pixels: int = 0


class MotionDetector:
    """
    Compare la frame courante avec la référence pour détecter :
    - Lancer (diff modérée → puis stabilisation)
    - Retrait (diff très grande)
    """

    def __init__(
        self,
        min_pixels: int = 200,      # Seuil bas : début de mouvement
        max_pixels: int = 30000,    # Seuil haut : retrait des fléchettes
        stable_frames: int = 4,     # Frames consécutives stables pour confirmer
        threshold: int = 20,        # Seuil binaire sur la différence
    ):
        self.min_pixels = min_pixels
        self.max_pixels = max_pixels
        self.stable_frames = stable_frames
        self.threshold = threshold

        self._reference: np.ndarray | None = None
        self._stable_count = 0
        self._in_motion = False

    def set_reference(self, frame: np.ndarray):
        """Définit la frame de référence (board sans fléchette)."""
        self._reference = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        self._reference = cv2.GaussianBlur(self._reference, (5, 5), 0)
        self._stable_count = 0
        self._in_motion = False

    def update_reference(self, frame: np.ndarray):
        """Met à jour la référence progressivement (moyenne glissante)."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        if self._reference is None:
            self._reference = gray
        else:
            # Fusion 90% ancien / 10% nouveau pour référence adaptative
            self._reference = cv2.addWeighted(self._reference, 0.9, gray, 0.1, 0)

    def process(self, frame: np.ndarray) -> MotionResult:
        """Traite une frame et retourne l'état de mouvement."""
        if self._reference is None:
            self.set_reference(frame)
            return MotionResult(state=MotionState.IDLE)

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)

        diff = cv2.absdiff(self._reference, gray)
        # Filtre bilatéral pour conserver les contours (fléchette) et supprimer le bruit
        diff = cv2.bilateralFilter(diff, 9, 75, 75)
        _, thresh = cv2.threshold(diff, self.threshold, 255, cv2.THRESH_BINARY)

        nonzero = cv2.countNonZero(thresh)

        # Retrait des fléchettes
        if nonzero > self.max_pixels:
            self._in_motion = False
            self._stable_count = 0
            return MotionResult(state=MotionState.TAKEOUT, diff_frame=thresh, nonzero_pixels=nonzero)

        # Mouvement (fléchette en vol)
        if nonzero > self.min_pixels:
            self._in_motion = True
            self._stable_count = 0
            return MotionResult(state=MotionState.MOTION_DETECTED, diff_frame=thresh, nonzero_pixels=nonzero)

        # Pas de mouvement
        if self._in_motion:
            self._stable_count += 1
            if self._stable_count >= self.stable_frames:
                # La fléchette est stable — déclencher l'analyse
                self._in_motion = False
                self._stable_count = 0
                return MotionResult(state=MotionState.DART_STABLE, diff_frame=thresh, nonzero_pixels=nonzero)

        return MotionResult(state=MotionState.IDLE, diff_frame=thresh, nonzero_pixels=nonzero)
