"""
Serveur FastAPI — point d'entrée principal.
Démarre le moteur de détection en tâche de fond.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import calibration, cameras, game
from api.events import event_bus
from detection.engine import DetectionEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from api.routes.cameras import camera_manager

    engine = DetectionEngine(camera_manager, event_bus)
    app.state.engine = engine
    task = asyncio.create_task(engine.run())

    print("=== DartSystem démarré ===", flush=True)
    logger.info("DartSystem API + moteur de détection démarrés")
    yield

    await engine.stop()
    task.cancel()
    camera_manager.stop_all()
    logger.info("DartSystem arrêté proprement")


app = FastAPI(title="DartSystem API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(calibration.router, prefix="/calibration", tags=["calibration"])
app.include_router(cameras.router,     prefix="/cameras",     tags=["cameras"])
app.include_router(game.router,        prefix="/game",        tags=["game"])


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


# Sert les pages web (dashboard, mobile, calibration) accessibles depuis le réseau.
# Téléphone → http://<IP_RPI>:8080/  (page mobile par défaut)
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_DASHBOARD = _Path(__file__).parent.parent / "dashboard"


_NO_CACHE = {"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"}


@app.get("/")
async def root():
    from fastapi.responses import FileResponse
    return FileResponse(str(_DASHBOARD / "game.html"), headers=_NO_CACHE)


@app.get("/ui/{page}")
async def ui_page(page: str):
    """Sert les pages HTML du dashboard sans cache (toujours la dernière version)."""
    from fastapi.responses import FileResponse, Response
    if ".." in page:
        return Response(status_code=404)
    path = _DASHBOARD / page
    if not path.exists():
        return Response(status_code=404)
    return FileResponse(str(path), headers=_NO_CACHE)


@app.post("/calibration/reload")
async def reload_calibrations():
    """Recharge les calibrations à chaud après recalibration depuis l'app."""
    app.state.engine.reload_calibrations()
    return {"success": True}
