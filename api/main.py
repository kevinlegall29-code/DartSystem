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


@app.post("/calibration/reload")
async def reload_calibrations():
    """Recharge les calibrations à chaud après recalibration depuis l'app."""
    app.state.engine.reload_calibrations()
    return {"success": True}
