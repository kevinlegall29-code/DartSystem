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

# Nombre de passes de détection moyennées (médiane) pour réduire le jitter
N_SAMPLES = 3

# Sauvegarde des images de debug (lourd : 6 warps + écriture disque par fléchette).
# Désactivé par défaut pour la fluidité — activer seulement pour le réglage.
DEBUG_VIZ = False
SAMPLE_DELAY = 0.03   # secondes entre passes de moyennage
POST_DART_COOLDOWN = 0.35   # garde-temps après une fléchette (évite re-détection)


def _touches_border(mask: np.ndarray, margin: int = 10, min_px: int = 60) -> bool:
    """
    True si le mouvement touche le bord de l'image (= bras/corps entrant
    depuis hors-champ). Une fléchette qui rebondit est intérieure.
    """
    if mask is None:
        return False
    h, w = mask.shape[:2]
    edges = (
        int(np.count_nonzero(mask[:margin])) +
        int(np.count_nonzero(mask[-margin:])) +
        int(np.count_nonzero(mask[:, :margin])) +
        int(np.count_nonzero(mask[:, -margin:]))
    )
    return edges > min_px


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
        self._motion_since = 0.0   # début du dernier mouvement non résolu (bounce-out)
        self._motion_was_arm = False  # le mouvement a-t-il touché le bord (bras) ?
        self._motion_accum: dict[int, np.ndarray] = {}  # masque mouvement accumulé par cam
        self._empty_reference: dict[int, np.ndarray] = {}  # board vide (pour valider retrait)

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
        # Le jeu peut réinitialiser le compteur de tour du moteur
        from api.game_logic import game
        game.engine_hook = self.reset_turn
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
                self._empty_reference[idx] = self._gray(processed)
        logger.info("Références de mouvement initialisées")

    def _gray(self, frame: np.ndarray) -> np.ndarray:
        g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return cv2.GaussianBlur(g, (5, 5), 0)

    def _process_motion(self, frames: dict) -> dict:
        """Traitement OpenCV du mouvement (sync, exécuté dans un thread)."""
        motion_results = {}
        for idx, frame in frames.items():
            if frame is None:
                continue
            processed = self._preprocess(frame, idx)
            result = self._motion[idx].process(processed)
            motion_results[idx] = (result, processed)
        return motion_results

    async def _detection_cycle(self):
        frames = self.cameras.read_all()
        # Le moteur tourne déjà dans son propre thread → calcul direct
        motion_results = self._process_motion(frames)

        # Détecte les états
        stable_cameras = [
            idx for idx, (r, _) in motion_results.items()
            if r.state == MotionState.DART_STABLE
        ]
        takeout_cameras = [
            idx for idx, (r, _) in motion_results.items()
            if r.state == MotionState.TAKEOUT
        ]
        motion_cameras = [
            idx for idx, (r, _) in motion_results.items()
            if r.state == MotionState.MOTION
        ]

        # --- Suivi bounce-out : fléchette qui touche puis ressort ---
        # Discriminateur clé : un BRAS entre par le BORD de l'image (rattaché au
        # joueur), une FLÉCHETTE qui rebondit est un petit objet INTÉRIEUR.
        now = time.time()
        if motion_cameras:
            if self._motion_since == 0.0:
                self._motion_since = now
                self._motion_was_arm = False
                self._motion_accum = {}
            # Détecte bord (bras) ET accumule la zone de mouvement (nouvelle fléchette)
            for idx, (r, _) in motion_results.items():
                if r.state == MotionState.MOTION and r.motion_mask is not None:
                    if _touches_border(r.motion_mask):
                        self._motion_was_arm = True
                    if idx in self._motion_accum:
                        self._motion_accum[idx] = cv2.bitwise_or(
                            self._motion_accum[idx], r.motion_mask)
                    else:
                        self._motion_accum[idx] = r.motion_mask.copy()
        else:
            if self._motion_since > 0.0:
                elapsed = now - self._motion_since
                max_ref = max((r.nonzero_ref for r, _ in motion_results.values()), default=0)
                board_empty = max_ref < self._motion[next(iter(self._motion))].min_dart_px
                recent_dart = (now - self._last_dart_time) < 1.5
                # Bounce-out = mouvement bref, INTÉRIEUR (pas un bras), board revenu vide
                if (elapsed < 1.2 and board_empty and not self._motion_was_arm
                        and not stable_cameras and not takeout_cameras and not recent_dart):
                    if self._darts_this_turn < MAX_DARTS_PER_TURN and \
                       (now - self._takeout_time) > self._takeout_cooldown:
                        self._motion_since = 0.0
                        self._motion_accum = {}
                        await self._handle_bounceout()
                        return
                self._motion_since = 0.0
                self._motion_was_arm = False
                self._motion_accum = {}

        # Log état toutes les ~5 secondes pour debug
        if not hasattr(self, '_debug_tick'):
            self._debug_tick = 0
        self._debug_tick += 1
        if self._debug_tick % 100 == 0:
            for idx, (r, _) in motion_results.items():
                print(f"[ENGINE] Cam{idx} état={r.state.value} consec={r.nonzero_consec} ref={r.nonzero_ref}", flush=True)

        # Cible déplacée / lumière changée : référence déjà recapturée par le détecteur
        board_changed = [
            idx for idx, (r, _) in motion_results.items()
            if r.state == MotionState.BOARD_CHANGED
        ]
        if board_changed:
            print(f"[ENGINE] Cible/lumière changée sur cams {board_changed} — référence recapturée", flush=True)
            for idx, (r, pf) in motion_results.items():
                if r.state == MotionState.BOARD_CHANGED:
                    self._empty_reference[idx] = self._gray(pf)
            return

        # Rafraîchit en continu les références tant qu'AUCUNE fléchette n'est sur
        # le board (idle). Auto-cicatrisation : si une référence est devenue
        # périmée (board bougé, fléchette restée), elle se remet à jour à vide.
        if (self._darts_this_turn == 0 and not stable_cameras
                and not takeout_cameras and not motion_cameras
                and (time.time() - self._takeout_time) > self._takeout_cooldown):
            for idx, (r, pf) in motion_results.items():
                if r.state == MotionState.IDLE:
                    g = self._gray(pf)
                    self._empty_reference[idx] = g
                    # Met à jour SEULEMENT la référence de travail (pas le suivi mouvement)
                    self._motion[idx]._reference = g

        # TAKEOUT seulement si AU MOINS 2 caméras le voient (évite faux positifs)
        if len(takeout_cameras) >= 2:
            print(f"[ENGINE] TAKEOUT sur cams {takeout_cameras}", flush=True)
            await self._handle_takeout()
            return

        # Ignore DART_STABLE pendant le cooldown post-retrait
        in_cooldown = (time.time() - self._takeout_time) < self._takeout_cooldown

        if stable_cameras:
            print(f"[ENGINE] DART_STABLE cams={stable_cameras} cooldown={in_cooldown}", flush=True)

        # Cooldown court après une fléchette pour éviter de la re-détecter
        post_dart = (time.time() - self._last_dart_time) < POST_DART_COOLDOWN

        if (stable_cameras and not in_cooldown and not post_dart
                and self._darts_this_turn < MAX_DARTS_PER_TURN):
            await asyncio.sleep(0.05)
            frames_stable = self.cameras.read_all()
            await self._handle_dart(frames_stable, stable_cameras)

    def _detect_pass(self, frames: dict):
        """Une passe de détection : retourne (result, detections, processed, thresh)."""
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
            gray = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (5, 5), 0)
            diff = cv2.absdiff(ref.astype(np.uint8), gray)
            _, thresh = cv2.threshold(diff, 22, 255, cv2.THRESH_BINARY)

            # ISOLATION : restreint à la zone de mouvement (la nouvelle fléchette).
            # Ignore les fléchettes statiques déjà plantées (pas de mouvement récent).
            accum = self._motion_accum.get(idx)
            if accum is not None and cv2.countNonZero(accum) > 30:
                # Dilate largement la zone de mouvement (le vol + la position finale)
                zone = cv2.dilate(accum, np.ones((45, 45), np.uint8), iterations=1)
                masked = cv2.bitwise_and(thresh, zone)
                # N'utilise le masquage que s'il reste assez de pixels (sinon fallback)
                if cv2.countNonZero(masked) > 60:
                    thresh = masked

            detections[idx] = detect_dart_location(thresh)
            processed_frames[idx] = processed
            thresh_frames[idx] = thresh

        result = fuse_detections(detections, self._homographies)
        return result, detections, processed_frames, thresh_frames

    async def _handle_dart(self, frames: dict, trigger_cameras: list[int]):
        """Localise (moyennage temporel) et score la fléchette, broadcast le résultat."""
        from detection import debug_viz
        from detection.scoring.board_mapping import position_to_score

        # MOYENNAGE TEMPOREL : plusieurs passes, on prend la médiane des positions
        # → réduit le jitter d'une frame qui fait basculer les cas-fils.
        samples = []
        result = None
        detections = processed_frames = thresh_frames = None
        for s in range(N_SAMPLES):
            r, det, pf, tf = self._detect_pass(self.cameras.read_all())
            if r is not None:
                samples.append((r.x_normalized, r.y_normalized))
                result, detections, processed_frames, thresh_frames = r, det, pf, tf
            if s < N_SAMPLES - 1:
                await asyncio.sleep(SAMPLE_DELAY)

        # Nettoie le suivi de mouvement (la fléchette est traitée)
        self._motion_since = 0.0
        self._motion_accum = {}

        # Position finale = médiane de la GRAPPE la plus dense (évite de moyenner
        # à travers un flip pointe/flight qui créerait un score fantôme au milieu).
        if samples:
            pts = np.array(samples)
            best_cluster = pts
            best_n = 0
            for p in pts:
                grp = pts[np.linalg.norm(pts - p, axis=1) < 50]
                if len(grp) > best_n:
                    best_n = len(grp)
                    best_cluster = grp
            med = np.median(best_cluster, axis=0)
            med_score = position_to_score(float(med[0]), float(med[1]))
            if result is not None:
                result.x_normalized = float(med[0])
                result.y_normalized = float(med[1])
                result.score = med_score
                if len(samples) >= 2:
                    logger.info(f"MÉDIANE-GRAPPE {best_n}/{len(samples)} passes → "
                                f"({med[0]:.0f},{med[1]:.0f}) = {med_score.label}")

        if detections is None:
            return

        # --- DEBUG : sauvegarde les images annotées (désactivé par défaut = fluidité) ---
        consensus = (result.x_normalized, result.y_normalized) if result else None
        for idx in (self._homographies if DEBUG_VIZ else {}):
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

        # Met à jour le jeu (501...) et broadcast l'état
        from api.game_logic import game
        if game.active:
            st = game.register_dart(result.score.label, result.score.score,
                                    result.score.multiplier)
            await self.event_bus.send_game_state(st)

        # Met à jour les références avec la fléchette plantée
        for idx in self._homographies:
            frame = frames.get(idx)
            if frame is not None:
                processed = self._preprocess(frame, idx)
                self._motion[idx].set_reference(processed)

    async def _handle_bounceout(self):
        """Fléchette qui a touché puis ressorti (bounce-out) = MISS, pas un retrait."""
        self._darts_this_turn += 1
        self._last_dart_time = time.time()
        print(f"[ENGINE] BOUNCE-OUT → MISS ({self._darts_this_turn}/3)", flush=True)
        logger.info(f"Bounce-out détecté → MISS ({self._darts_this_turn}/3)")
        await self.event_bus.send_dart(
            score_label="MISS", score_value=0,
            camera_info={"bounceout": True, "confidence": 1.0},
        )
        from api.game_logic import game
        if game.active:
            st = game.register_dart("MISS", 0, 0)
            await self.event_bus.send_game_state(st)

    async def _handle_takeout(self):
        """Retrait des fléchettes → fin de tour. Modèle simple et robuste."""
        self._motion_since = 0.0
        self._motion_accum = {}

        if self._darts_this_turn == 0:
            self._takeout_time = time.time()
            return   # rien à retirer

        # Anti-faux-positif : pas de takeout juste après une fléchette (mi-lancer).
        # Un retrait survient quand le joueur a fini de lancer (≥1s après le dernier dart).
        if time.time() - self._last_dart_time < 1.0:
            return

        self._takeout_time = time.time()
        logger.info(f"Retrait après {self._darts_this_turn} fléchette(s)")
        self._darts_this_turn = 0
        await self.event_bus.send_takeout()

        # Fin de tour côté jeu → joueur suivant
        from api.game_logic import game
        if game.active:
            st = game.end_turn()
            await self.event_bus.send_game_state(st)

        # Attend la stabilité puis recapture les références (nouveau board vide)
        await self._wait_until_stable()
        frames = self.cameras.read_all()
        for idx, frame in frames.items():
            if frame is not None:
                processed = self._preprocess(frame, idx)
                self._motion[idx].set_reference(processed)
                self._empty_reference[idx] = self._gray(processed)
        logger.info("Référence board vide recapturée")

    def reset_turn(self):
        """Réinitialise le compteur de fléchettes du tour (appelé par le jeu)."""
        self._darts_this_turn = 0
        self._motion_since = 0.0
        self._motion_accum = {}

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
