import cv2
import threading
import logging
import time

logger = logging.getLogger(__name__)


class CameraStream:
    """Capture asynchrone d'une caméra USB (OV9732)."""

    def __init__(self, index: int, width: int = 1280, height: int = 720, fps: int = 30, exposure: int = 156, rotate180: bool = False):
        self.index = index
        self.rotate180 = rotate180
        self.width = width
        self.height = height
        self.fps = fps
        self.exposure = exposure

        self._cap: cv2.VideoCapture | None = None
        self._frame = None
        self._lock = threading.Lock()
        self._stopped = False
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    def start(self) -> "CameraStream":
        self._cap = cv2.VideoCapture(self.index)
        if not self._cap.isOpened():
            raise RuntimeError(f"Impossible d'ouvrir la caméra {self.index}")

        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._cap.set(cv2.CAP_PROP_FPS, self.fps)
        # V4L2 : 1 = manuel, 3 = auto
        self._cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)
        # Exposition fixe identique pour toutes les caméras (ajustable)
        self._cap.set(cv2.CAP_PROP_EXPOSURE, self.exposure)

        ok, frame = self._cap.read()
        if not ok:
            raise RuntimeError(f"Caméra {self.index} : première frame impossible à lire")
        self._frame = frame

        self._stopped = False
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.info(f"Caméra {self.index} démarrée ({self.width}×{self.height} @ {self.fps}fps)")
        return self

    def _capture_loop(self):
        while not self._stopped:
            ok, frame = self._cap.read()
            if ok:
                with self._lock:
                    self._frame = frame

    def read(self):
        """Retourne la dernière frame disponible (retournée si rotate180=True)."""
        with self._lock:
            if self._frame is None:
                return None
            frame = self._frame.copy()
            if self.rotate180:
                frame = cv2.rotate(frame, cv2.ROTATE_180)
            return frame

    def stop(self):
        self._stopped = True
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._cap:
            self._cap.release()
        logger.info(f"Caméra {self.index} arrêtée")

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def __enter__(self):
        return self.start()

    def __exit__(self, *_):
        self.stop()


class CameraManager:
    """Gère les 3 caméras OV9732.
    device_indices : indices réels des devices (ex: 0, 2, 4 pour video0/video2/video4)
    Les clés du dict sont toujours 0, 1, 2 pour le dashboard et l'API.
    """

    def __init__(self, device_indices: tuple = (0, 2, 4), rotate180: tuple = (False, False, False)):
        self.cameras: dict[int, CameraStream] = {
            slot: CameraStream(index=dev_idx, rotate180=rot)
            for slot, (dev_idx, rot) in enumerate(zip(device_indices, rotate180))
        }

    def start_all(self):
        errors = []
        for idx, cam in self.cameras.items():
            try:
                cam.start()
            except RuntimeError as e:
                errors.append(str(e))
                logger.error(f"Caméra {idx} : {e}")
        if errors:
            logger.warning(f"{len(errors)} caméra(s) non disponible(s)")

    def stop_all(self):
        for cam in self.cameras.values():
            cam.stop()

    def read_all(self) -> dict[int, any]:
        return {idx: cam.read() for idx, cam in self.cameras.items()}

    def status(self) -> dict[int, bool]:
        return {idx: cam.is_alive() for idx, cam in self.cameras.items()}
