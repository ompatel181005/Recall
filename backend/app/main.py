"""TranscribeAI API entrypoint.

Dev: uvicorn app.main:app --reload --port 8000 (frontend dev server proxies /api).
Prod: also serves the built frontend from frontend/dist if present.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import REPO_ROOT, settings
from .db import init_db
from .routers import courses, lectures
from .services import jobs, media
from .services.providers.registry import provider_status
from .services.transcribe import cuda_available


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="TranscribeAI", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "providers": provider_status(),
        "cuda": cuda_available(),
        "tasks": settings.tasks,
        "transcription_model": settings.transcription.get("model", ""),
        "ffmpeg": media.ffmpeg_available(),
        "queue_depth": jobs.queue_depth(),
    }


app.include_router(courses.router)
app.include_router(lectures.router)

_frontend_dist = REPO_ROOT / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
