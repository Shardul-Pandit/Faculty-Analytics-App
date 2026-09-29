import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .core.config import settings
from .core.database import Base, engine
from .routes import analysis, auth, files, mappings

logger = logging.getLogger("uvicorn.access")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create DB tables and storage directories on first start."""
    Base.metadata.create_all(bind=engine)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    settings.outputs_dir.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title       = "Faculty Analytics API",
    description = "Backend for the Faculty Student Assessment Analytics application.",
    version     = "1.0.0",
    lifespan    = lifespan,
)

app.add_middleware(
    CORSMiddleware,
    # Accept both localhost and 127.0.0.1 — browsers treat them as different origins
    allow_origins      = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        # Fallback ports used when 3000 is occupied by another process
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3002",
    ],
    allow_credentials  = True,
    allow_methods      = ["*"],
    allow_headers      = ["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    origin = request.headers.get("origin", "—")
    start  = time.time()
    response = await call_next(request)
    ms = int((time.time() - start) * 1000)
    logger.info(
        "%s %s | origin=%s | status=%s | %dms",
        request.method, request.url.path,
        origin, response.status_code, ms,
    )
    return response


app.include_router(auth.router)
app.include_router(files.router)
app.include_router(mappings.router)
app.include_router(analysis.router)


@app.get("/health", tags=["health"])
def health():
    from .services.analysis_service import _ai_available, _openai_available
    return {
        "status":           "ok",
        "app":              settings.app_name,
        "ai_provider":      settings.ai_provider,
        "ai_configured":    _ai_available(),
        # Legacy key retained so older frontend code doesn't break
        "openai_configured": _openai_available(),
    }
