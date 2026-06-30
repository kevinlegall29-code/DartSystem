"""
Détection de mouvement par comparaison de frames consécutives.

Logique :
- Compare frame[T] vs frame[T-1] pour détecter si la scène bouge
- Quand la scène se stabilise après un mouvement → fléchette plantée
- Compare frame stable vs référence (board vide) pour localiser la fléchette
"""

import cv2
import numpy as np
import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class MotionState(Enum):
    IDLE          = "idle"     # Pas de mouvement, board vide
    MOTION        = "motion"   # Mouvement détecté (fléchette en vol)
    DART_STABLE   = "stable"   # Fléchette plantée et immobile → analyser
    TAKEOUT       = "takeout"  # Grand mouvement = retrait des fléchettes
    BOARD_CHANGED = "board"    # Cible déplacée / lumière changée → réf recapturée


@dataclass
class MotionResult:
    state:           MotionState
    diff_ref:        np.ndarray | None = None   # diff avec référence (board vide)
    nonzero_consec:  int = 0                    # pixels qui bougent entre T-1 et T
    nonzero_ref:     int = 0                    # pixels différents vs référence
    motion_mask:     np.ndarray | None = None   # masque du mouvement consécutif (T-1→T)


class MotionDetector:
    """
    Détecte les fléchettes en comparant frames consécutives (stabilité)
    et avec la référence board-vide (localisation).
    """

    def __init__(
        self,
        # Seuils sur frames consécutives (mouvement)
        min_motion_px:  int = 150,    # Minimum pour considérer qu'il y a du mouvement
        max_motion_px:  int = 40000,  # Au-delà = retrait des fléchettes
        stable_frames:  int = 3,      # Frames consécutives calmes pour confirmer
        motion_thresh:  int = 15,     # Seuil binaire sur diff consécutive
        # Seuil sur diff avec référence (dart visible)
        ref_thresh:     int = 25,     # Seuil binaire sur diff avec board vide
        min_dart_px:    int = 100,    # Pixels min pour qu'une fléchette soit visible
        max_ref_px:     int = 20000,  # Au-delà = cible déplacée/lumière (pas une fléchette)
    ):
        self.min_motion_px = min_motion_px
        self.max_motion_px = max_motion_px
        self.stable_frames = stable_frames
        self.motion_thresh = motion_thresh
        self.ref_thresh    = ref_thresh
        self.min_dart_px   = min_dart_px
        self.max_ref_px    = max_ref_px

        self._reference:  np.ndarray | None = None   # Board vide (gris+blur)
        self._prev_frame: np.ndarray | None = None   # Frame T-1 (gris+blur)
        self._in_motion   = False
        self._stable_count = 0

    # ------------------------------------------------------------------

    def set_reference(self, frame: np.ndarray):
        """Mémorise le board vide comme référence."""
        gray = self._to_gray(frame)
        self._reference  = gray
        self._prev_frame = gray
        self._in_motion  = False
        self._stable_count = 0

    def process(self, frame: np.ndarray) -> MotionResult:
        gray = self._to_gray(frame)

        if self._reference is None or self._prev_frame is None:
            self.set_reference(frame)
            return MotionResult(state=MotionState.IDLE)

        # --- Diff consécutive (T-1 → T) : détecte si ça bouge encore ---
        diff_consec = cv2.absdiff(self._prev_frame, gray)
        _, thresh_consec = cv2.threshold(diff_consec, self.motion_thresh, 255, cv2.THRESH_BINARY)
        nonzero_consec = cv2.countNonZero(thresh_consec)

        # --- Diff avec référence : montre où est la fléchette ---
        diff_ref = cv2.absdiff(self._reference, gray)
        _, thresh_ref = cv2.threshold(diff_ref, self.ref_thresh, 255, cv2.THRESH_BINARY)
        nonzero_ref = cv2.countNonZero(thresh_ref)

        # Toujours mettre à jour la frame précédente
        self._prev_frame = gray

        # --- Machine à états ---

        # Grand mouvement = retrait
        if nonzero_consec > self.max_motion_px:
            self._in_motion    = False
            self._stable_count = 0
            return MotionResult(MotionState.TAKEOUT, thresh_ref, nonzero_consec, nonzero_ref)

        # Mouvement normal (fléchette en vol)
        if nonzero_consec > self.min_motion_px:
            self._in_motion    = True
            self._stable_count = 0
            return MotionResult(MotionState.MOTION, thresh_ref, nonzero_consec, nonzero_ref,
                                motion_mask=thresh_consec)

        # Diff énorme avec la référence + scène stable = la cible a bougé ou
        # la lumière a changé (PAS une fléchette). On recapture la référence.
        if nonzero_consec < self.min_motion_px and nonzero_ref > self.max_ref_px:
            self._stable_count += 1
            if self._stable_count >= self.stable_frames:
                self._reference = gray            # accepte le nouvel état comme référence
                self._in_motion = False
                self._stable_count = 0
                return MotionResult(MotionState.BOARD_CHANGED, thresh_ref, nonzero_consec, nonzero_ref)
            return MotionResult(MotionState.IDLE, thresh_ref, nonzero_consec, nonzero_ref)

        # Scène calme
        if self._in_motion:
            # Était en mouvement, maintenant stable → fléchette posée ?
            if self.min_dart_px <= nonzero_ref <= self.max_ref_px:
                self._stable_count += 1
                if self._stable_count >= self.stable_frames:
                    self._in_motion    = False
                    self._stable_count = 0
                    return MotionResult(MotionState.DART_STABLE, thresh_ref, nonzero_consec, nonzero_ref)
            else:
                # Rien de visible OU diff trop grande → faux positif, reset
                self._in_motion    = False
                self._stable_count = 0

        return MotionResult(MotionState.IDLE, thresh_ref, nonzero_consec, nonzero_ref)

    def _to_gray(self, frame: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return cv2.GaussianBlur(gray, (5, 5), 0)
