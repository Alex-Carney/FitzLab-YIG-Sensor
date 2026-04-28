"""FastAPI app factory + lifespan."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.auth import SessionInvalidError, verify_session_cookie
from app.config import Settings
from app.db import Database
from app.routes import api as api_routes
from app.routes import auth as auth_routes
from app.routes import health as health_routes
from app.routes import ws as ws_routes
from app.watcher import PollingWatcher
from app.ws_manager import ConnectionManager


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def build_app() -> FastAPI:
    load_dotenv(override=False)
    settings = Settings.from_env()
    _configure_logging(settings.log_level)
    logger = logging.getLogger("yig.main")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("opening DB at %s", settings.db_path)
        db = Database(settings.db_path)
        db.connect(max_wait_sec=settings.db_connect_max_wait_sec)
        manager = ConnectionManager()
        watcher = PollingWatcher(
            db=db, manager=manager, cadence_sec=settings.cadence_sec
        )
        watcher_task = asyncio.create_task(watcher.run())

        app.state.settings = settings
        app.state.db = db
        app.state.manager = manager
        app.state.watcher = watcher

        try:
            yield
        finally:
            logger.info("shutting down watcher and DB")
            watcher.stop()
            try:
                await asyncio.wait_for(watcher_task, timeout=2.0)
            except asyncio.TimeoutError:
                watcher_task.cancel()
            db.close()

    app = FastAPI(title="YIG Streaming Dashboard", lifespan=lifespan)
    app.include_router(health_routes.router)
    app.include_router(auth_routes.router)
    app.include_router(api_routes.router)
    app.include_router(ws_routes.router)

    frontend_dir = Path(__file__).resolve().parent.parent / "frontend"

    if frontend_dir.exists():
        app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

        @app.get("/login", include_in_schema=False)
        async def login_page():
            return FileResponse(frontend_dir / "login.html")

        @app.get("/", include_in_schema=False)
        async def root(request: Request):
            cookie = request.cookies.get(settings.cookie_name)
            try:
                verify_session_cookie(settings.secret, cookie)
            except SessionInvalidError:
                return RedirectResponse(url="/login", status_code=303)
            return FileResponse(frontend_dir / "index.html")

    return app


# Use uvicorn's factory mode so env vars can be controlled at startup:
#   uvicorn --factory app.main:build_app --host 127.0.0.1 --port 8000
