"""Media generation endpoints: local image, video, and sound effects.

Heavy work (image/video) runs as background jobs — one at a time behind a
shared lock so generation can never exhaust the machine. Sound effects are
instant and synchronous.
"""

from __future__ import annotations

import asyncio
import itertools
import threading

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

media_router = APIRouter()

_job_counter = itertools.count(1)
_jobs: dict[int, dict] = {}
_heavy_lock = threading.Lock()


class ImageBody(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    model: str = "sdxs-512"
    size: int = 512
    steps: int | None = None
    seed: int | None = None


class VideoBody(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    model: str = "sdxs-512"
    seconds: float = 4.0
    motion: str = "zoom"
    seed: int | None = None


class SfxBody(BaseModel):
    prompt: str = Field(min_length=1, max_length=500)
    duration: float = 3.0
    intensity: float = 0.6
    seed: int | None = None


class DownloadBody(BaseModel):
    model: str = "sdxs-512"


def _new_job(kind: str) -> int:
    job_id = next(_job_counter)
    _jobs[job_id] = {"state": "running", "percent": 0, "error": None, "generation_id": None,
                     "kind": kind}
    # Keep the registry small; finished jobs older than the last 50 vanish.
    for old in sorted(_jobs)[:-50]:
        if _jobs[old]["state"] != "running":
            _jobs.pop(old, None)
    return job_id


def _run_heavy(job_id: int, work) -> None:
    """Runs in a worker thread: serialize heavy jobs, capture progress/errors."""
    job = _jobs[job_id]
    if not _heavy_lock.acquire(blocking=False):
        job.update(state="error", error="another generation is already running — try again shortly")
        return
    try:
        job["generation_id"] = work(lambda p: job.__setitem__("percent", round(p * 100)))
        job.update(state="done", percent=100)
    except Exception as exc:  # noqa: BLE001 - job errors must reach the UI, not crash the app
        job.update(state="error", error=str(exc))
    finally:
        _heavy_lock.release()


@media_router.get("/media/profile")
def media_profile(request: Request) -> dict:
    return request.app.state.media_profile


@media_router.get("/media/image/models")
def image_models(request: Request) -> list[dict]:
    return request.app.state.image_engine.catalog()


@media_router.post("/media/image/models/download")
async def download_image_model(request: Request, body: DownloadBody) -> dict:
    engine = request.app.state.image_engine
    if engine.download.active:
        raise HTTPException(409, "a model download is already in progress")
    try:
        await asyncio.to_thread(engine.download_model, body.model)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - surface as clean API error
        raise HTTPException(502, f"download failed: {exc}") from exc
    return {"ok": True, "installed": engine.is_installed(body.model)}


@media_router.get("/media/image/models/download/status")
def download_status(request: Request) -> dict:
    return request.app.state.image_engine.download_status()


@media_router.post("/media/image/generate")
async def generate_image(request: Request, body: ImageBody) -> dict:
    engine = request.app.state.image_engine
    store = request.app.state.media_store
    if not engine.is_installed(body.model):
        raise HTTPException(409, "image model not downloaded yet")
    job_id = _new_job("image")

    def work(progress) -> int:
        png = engine.generate(
            body.model, body.prompt, size=body.size, steps=body.steps, seed=body.seed,
            progress=progress,
        )
        row = store.add(
            "image", body.prompt,
            {"model": body.model, "size": body.size, "steps": body.steps, "seed": body.seed},
            png,
        )
        return row["id"]

    asyncio.get_running_loop().run_in_executor(None, _run_heavy, job_id, work)
    return {"job_id": job_id}


@media_router.post("/media/video/generate")
async def generate_video(request: Request, body: VideoBody) -> dict:
    image_engine = request.app.state.image_engine
    video_engine = request.app.state.video_engine
    store = request.app.state.media_store
    if not image_engine.is_installed(body.model):
        raise HTTPException(409, "image model not downloaded yet — video uses it for keyframes")
    job_id = _new_job("video")

    def work(progress) -> int:
        clip = video_engine.generate(
            body.model, body.prompt, seconds=body.seconds, motion=body.motion, seed=body.seed,
            progress=progress,
        )
        row = store.add(
            "video", body.prompt,
            {"model": body.model, "seconds": body.seconds, "motion": body.motion, "seed": body.seed},
            clip,
        )
        return row["id"]

    asyncio.get_running_loop().run_in_executor(None, _run_heavy, job_id, work)
    return {"job_id": job_id}


@media_router.get("/media/jobs/{job_id}")
def job_status(job_id: int) -> dict:
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job


@media_router.post("/media/sfx/generate")
def generate_sfx(request: Request, body: SfxBody) -> dict:
    from ..media.sfx import synthesize_sfx

    wav, categories = synthesize_sfx(body.prompt, body.duration, body.intensity, body.seed)
    row = request.app.state.media_store.add(
        "sfx", body.prompt,
        {"duration": body.duration, "intensity": body.intensity, "seed": body.seed,
         "categories": categories},
        wav,
    )
    return row


@media_router.get("/media/generations")
def list_generations(request: Request, kind: str | None = None) -> list[dict]:
    return request.app.state.media_store.list(kind)


@media_router.delete("/media/generations/{row_id}")
def delete_generation(request: Request, row_id: int) -> dict:
    if not request.app.state.media_store.delete(row_id):
        raise HTTPException(404, "generation not found")
    return {"ok": True}


@media_router.get("/media/generations/{row_id}/file")
def generation_file(request: Request, row_id: int) -> FileResponse:
    path = request.app.state.media_store.file_path(row_id)
    if path is None:
        raise HTTPException(404, "file not found")
    media_types = {".png": "image/png", ".gif": "image/gif", ".wav": "audio/wav"}
    return FileResponse(path, media_type=media_types.get(path.suffix, "application/octet-stream"))
