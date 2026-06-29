"""
Moteur principal de détection.
Orchestre : caméras → motion → corners → fusion → score → WebSocket.
"""

import asyncio
import logging
import time
from pathlib import Path

import cv2
import numpy as np

from detection.cameras.stream import CameraManager
from detection.calibration.lens import load_lens_calibration, undistort
from detection.calibration.board import load_board_calibration, normalize_frame
from detection.detection.motion import MotionDetector, MotionState
from detection.detection.corners import detect_dart_location
from detection.detection.fusion import fuse_detections
from detection.scoring.board_mapping import DartScore

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data" / "calibrations"

# Caméras utilisées pour la localisation de la pointe (pas la caméra du dessus = slot 1)
TIP_CAMERAS = {0, 2}   # CAM0 (bas-gauche) et CAM2 (bas-droite) seulement

# Délai max entre détection d'une caméra et les autres (secondes)
SYNC_WINDOW = 0.3

# Nombre max de fléchettes par tour
MAX_DARTS_PER_TURN = 3


class DetectionEngine:
    """
    Boucle principale de détection.
    S'exécute dans un thread asyncio séparé.
    """

    def __init__(self, camera_manager: CameraManager, event_bus):
        self.cameras = camera_manager
        self.event_bus = event_bus

        # Un détecteur de mouvement par caméra
        self._motion: dict[int, MotionDetector] = {
            idx: MotionDetector() for idx in camera_manager.cameras
        }

        # Calibrations chargées au démarrage
        self._lens: dict[int, tuple] = {}
        self._homographies: dict[int, np.ndarray] = {}

        self._running = False
        self._darts_this_turn = 0
        self._last_dart_time = 0.0
        self._takeout_time = 0.0   # timestamp du dernier retrait
        self._takeout_cooldown = 1.5  # secondes à ignorer après retrait

    # ------------------------------------------------------------------
    # Cycle de vie
    # ------------------------------------------------------------------

    def load_calibrations(self):
        """Charge toutes les calibrations disponibles depuis le disque."""
        for idx in self.cameras.cameras:
            # Distorsion lentille
            try:
                K, D = load_lens_calibration(idx, DATA_DIR)
                self._lens[idx] = (K, D)
                logger.info(f"Calibration lentille chargée — cam {idx}")
            except FileNotFoundError:
                logger.warning(f"Pas de calibration lentille pour cam {idx} — distorsion non corrigée")

            # Homographie board
            try:
                cal = load_board_calibration(idx, DATA_DIR)
                self._homographies[idx] = cal["homography"]
                logger.info(f"Calibration board chargée — cam {idx}")
            except FileNotFoundError:
                logger.warning(f"Pas de calibration board pour cam {idx} — caméra ignorée")

    def reload_calibrations(self):
        """Recharge les calibrations à chaud (après recalibration depuis l'app)."""
        self._lens.clear()
        self._homographies.clear()
        self.load_calibrations()

    async def run(self):
        """Boucle principale asynchrone. Appeler avec asyncio.create_task()."""
        print("[ENGINE] Démarrage...", flush=True)
        self.load_calibrations()
        self._running = True
        print(f"[ENGINE] Caméras : {list(self.cameras.cameras.keys())}", flush=True)
        print(f"[ENGINE] Homographies chargées : {list(self._homographies.keys())}", flush=True)

        await self._init_references()
        print("[ENGINE] Références initialisées, détection active", flush=True)

        cycle = 0
        while self._running:
            try:
                await self._detection_cycle()
            except Exception as e:
                print(f"[ENGINE] Erreur cycle : {e}", flush=True)
                logger.error(f"Erreur cycle détection : {e}", exc_info=True)
            cycle += 1
            if cycle % 100 == 0:
                print(f"[ENGINE] Cycle {cycle} — toujours actif", flush=True)
            await asyncio.sleep(0.05)   # ~20 Hz

    async def stop(self):
        self._running = False
        logger.info("Moteur de détection arrêté")

    # ------------------------------------------------------------------
    # Cycle de détection
    # ------------------------------------------------------------------

    async def _init_references(self):
        """Capture les frames initiales comme référence (board vide)."""
        await asyncio.sleep(1.0)   # Laisse les caméras se stabiliser
        frames = self.cameras.read_all()
        for idx, frame in frames.items():
            if frame is not None:
                processed = self._preprocess(frame, idx)
                self._motion[idx].set_reference(processed)
        logger.info("Références de mouvement initialisées")

    async def _detection_cycle(self):
        frames = self.cameras.read_all()
        motion_results = {}

        for idx, frame in frames.items():
            if frame is None:
                continue
            processed = self._preprocess(frame, idx)
            result = self._motion[idx].process(processed)
            motion_results[idx] = (result, processed)

        # Détecte les états
        stable_cameras = [
            idx for idx, (r, _) in motion_results.items()
            if r.state == MotionState.DART_STABLE
        ]
        takeout_cameras = [
            idx for idx, (r, _) in motion_results.items()
            if r.state == MotionState.TAKEOUT
        ]

        # Log état toutes les ~5 secondes pour debug
        if not hasattr(self, '_debug_tick'):
            self._debug_tick = 0
        self._debug_tick += 1
        if self._debug_tick % 100 == 0:
            for idx, (r, _) in motion_results.items():
                print(f"[ENGINE] Cam{idx} état={r.state.value} consec={r.nonzero_consec} ref={r.nonzero_ref}", flush=True)

        # TAKEOUT seulement si AU MOINS 2 caméras le voient (évite faux positifs)
        if len(takeout_cameras) >= 2:
            print(f"[ENGINE] TAKEOUT sur cams {takeout_cameras}", flush=True)
            await self._handle_takeout()
            return

        # Ignore DART_STABLE pendant le cooldown post-retrait
        in_cooldown = (time.time() - self._takeout_time) < self._takeout_cooldown

        if stable_cameras:
            print(f"[ENGINE] DART_STABLE cams={stable_cameras} cooldown={in_cooldown}", flush=True)

        if stable_cameras and not in_cooldown and self._darts_this_turn < MAX_DARTS_PER_TURN:
            # Attend brièvement que les autres caméras se stabilisent aussi
            await asyncio.sleep(0.1)
            frames_stable = self.cameras.read_all()
            await self._handle_dart(frames_stable, stable_cameras)

    async def _handle_dart(self, frames: dict, trigger_cameras: list[int]):
        """Localise et score la fléchette, broadcast le résultat."""
        from detection import debug_viz
        from detection.detection.fusion import find_tip_normalized

        detections = {}
        processed_frames = {}
        thresh_frames = {}

        for idx in self._homographies:

            frame = frames.get(idx)
            if frame is None:
                continue

            processed = self._preprocess(frame, idx)
            ref = self._motion[idx]._reference

            if ref is None:
                continue

            # Différence avec la référence
            gray = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (5, 5), 0)
            diff = cv2.absdiff(ref.astype(np.uint8), gray)
            # Seuil bas pour capter aussi le fût sombre qui se fond dans le board noir
            _, thresh = cv2.threshold(diff, 22, 255, cv2.THRESH_BINARY)

            location = detect_dart_location(thresh)
            detections[idx] = location
            processed_frames[idx] = processed
            thresh_frames[idx] = thresh

        result = fuse_detections(detections, self._homographies)

        # --- DEBUG : sauvegarde les images annotées avec le consensus final ---
        consensus = (result.x_normalized, result.y_normalized) if result else None
        for idx in self._homographies:
            if idx not in processed_frames:
                continue
            try:
                loc = detections.get(idx)
                endpoints = loc.corners if loc else None
                tip_norm = None
                tip_cam = None
                if loc and endpoints is not None and len(endpoints) >= 2:
                    tip_cam = endpoints[0]   # corners[0] = pointe (bout fin)
                    tn = cv2.perspectiveTransform(
                        tip_cam.reshape(1, 1, 2).astype(np.float32),
                        self._homographies[idx])[0][0]
                    tip_norm = (float(tn[0]), float(tn[1]))
                debug_viz.save_camera_detection(idx, processed_frames[idx], thresh_frames[idx], endpoints, tip_cam)
                debug_viz.save_normalized_view(
                    idx, processed_frames[idx], self._homographies[idx],
                    tip_norm, "", both_endpoints=endpoints, consensus=consensus)
            except Exception as e:
                print(f"[DEBUG] Erreur viz cam{idx}: {e}", flush=True)

        if result is None:
            logger.debug("Fusion : aucune détection exploitable")
            return

        self._darts_this_turn += 1
        self._last_dart_time = time.time()

        logger.info(
            f"Fléchette {self._darts_this_turn}/3 : {result.score.label} "
            f"({result.score.score}pts) conf={result.confidence:.2f} "
            f"cams={result.cameras_used} accord={result.agreement}"
        )

        await self.event_bus.send_dart(
            score_label=result.score.label,
            score_value=result.score.score,
            camera_info={
                "cameras_used": result.cameras_used,
                "confidence": round(result.confidence, 3),
                "agreement": result.agreement,
                "x": round(result.x_normalized, 1),
                "y": round(result.y_normalized, 1),
            },
        )

        # Met à jour les références avec la fléchette plantée
        for idx in self._homographies:
            frame = frames.get(idx)
            if frame is not None:
                processed = self._preprocess(frame, idx)
                self._motion[idx].set_reference(processed)

    async def _handle_takeout(self):
        """Reset après retrait des fléchettes."""
        self._takeout_time = time.time()   # Démarre le cooldown

        if self._darts_this_turn == 0:
            return   # Faux positif, ignore

        logger.info(f"Retrait détecté après {self._darts_this_turn} fléchette(s)")
        self._darts_this_turn = 0

        await self.event_bus.send_takeout()

        # Attend que la scène soit RÉELLEMENT stable (bras parti) avant de
        # capturer la nouvelle référence du board vide.
        await self._wait_until_stable()

        frames = self.cameras.read_all()
        for idx, frame in frames.items():
            if frame is not None:
                processed = self._preprocess(frame, idx)
                self._motion[idx].set_reference(processed)
        logger.info("Référence board vide recapturée après stabilisation")

    async def _wait_until_stable(self, needed: int = 6, timeout: float = 6.0):
        """Attend N frames consécutives sans mouvement (bras hors champ)."""
        prev = {}
        stable = 0
        start = time.time()
        while time.time() - start < timeout:
            await asyncio.sleep(0.05)
            frames = self.cameras.read_all()
            moving = False
            for idx, frame in frames.items():
                if frame is None:
                    continue
                gray = cv2.cvtColor(self._preprocess(frame, idx), cv2.COLOR_BGR2GRAY)
                gray = cv2.GaussianBlur(gray, (5, 5), 0)
                if idx in prev:
                    diff = cv2.absdiff(prev[idx], gray)
                    _, th = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
                    if cv2.countNonZero(th) > 400:
                        moving = True
                prev[idx] = gray
            stable = stable + 1 if not moving else 0
            if stable >= needed:
                return

    # ------------------------------------------------------------------
    # Prétraitement
    # ------------------------------------------------------------------

    def _preprocess(self, frame: np.ndarray, cam_idx: int) -> np.ndarray:
        """Corrige la distorsion si calibration disponible."""
        if cam_idx in self._lens:
            K, D = self._lens[cam_idx]
            return undistort(frame, K, D)
        return frame
