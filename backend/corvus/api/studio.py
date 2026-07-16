"""Voice Studio endpoints: voices catalog, generation, history, playback."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..voice import studio

studio_router = APIRouter()


class GenerateBody(BaseModel):
    text: str
    engine: str = "edge"
    voice: str
    rate: int = Field(0, ge=-50, le=100)    # ±% speed
    pitch: int = Field(0, ge=-50, le=50)    # ±Hz (edge only)
    volume: int = Field(0, ge=-50, le=50)   # ±% (edge only)


class PreviewBody(BaseModel):
    engine: str = "edge"
    voice: str


class PiperDownloadBody(BaseModel):
    voice: str


def _validate(body: GenerateBody) -> str:
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "text is empty")
    if len(text) > studio.MAX_TEXT_CHARS:
        raise HTTPException(400, f"text exceeds {studio.MAX_TEXT_CHARS} characters")
    if body.engine not in ("edge", "piper"):
        raise HTTPException(400, f"unknown engine: {body.engine}")
    return text


@studio_router.get("/studio/voices")
async def voices() -> dict:
    return {"edge": await studio.edge_voices(), "piper": studio.piper_catalog()}


@studio_router.post("/studio/generate")
async def generate(request: Request, body: GenerateBody) -> dict:
    text = _validate(body)
    try:
        audio, ext = await studio.synthesize(
            body.engine, text, body.voice, body.rate, body.pitch, body.volume
        )
    except FileNotFoundError as exc:
        raise HTTPException(409, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"synthesis failed: {exc}")

    filename = f"{datetime.now():%Y%m%d-%H%M%S}-{body.voice}.{ext}"
    (studio.voiceovers_dir() / filename).write_bytes(audio)
    return request.app.state.repo.add_voiceover(
        text, body.engine, body.voice, body.rate, body.pitch, body.volume, filename
    )


@studio_router.post("/studio/preview")
async def preview(body: PreviewBody) -> Response:
    if body.engine not in ("edge", "piper"):
        raise HTTPException(400, f"unknown engine: {body.engine}")
    try:
        audio, ext = await studio.synthesize(body.engine, studio.PREVIEW_TEXT, body.voice)
    except FileNotFoundError as exc:
        raise HTTPException(409, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"preview failed: {exc}")
    return Response(audio, media_type="audio/mpeg" if ext == "mp3" else "audio/wav")


@studio_router.get("/studio/generations")
def generations(request: Request) -> list[dict]:
    return request.app.state.repo.list_voiceovers()


@studio_router.get("/studio/generations/{voiceover_id}/audio")
def audio(request: Request, voiceover_id: int) -> FileResponse:
    row = request.app.state.repo.get_voiceover(voiceover_id)
    if row is None:
        raise HTTPException(404, "voiceover not found")
    path = studio.voiceovers_dir() / row["filename"]
    if not path.exists():
        raise HTTPException(404, "audio file is missing")
    media = "audio/mpeg" if path.suffix == ".mp3" else "audio/wav"
    return FileResponse(path, media_type=media, filename=row["filename"])


@studio_router.delete("/studio/generations/{voiceover_id}")
def delete(request: Request, voiceover_id: int) -> dict:
    row = request.app.state.repo.get_voiceover(voiceover_id)
    if row is None:
        raise HTTPException(404, "voiceover not found")
    (studio.voiceovers_dir() / row["filename"]).unlink(missing_ok=True)
    request.app.state.repo.delete_voiceover(voiceover_id)
    return {"ok": True}


@studio_router.post("/studio/piper/download")
async def piper_download(body: PiperDownloadBody) -> dict:
    try:
        await studio.piper_download(body.voice)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"download failed: {exc}")
    return {"ok": True, "installed": studio.piper_installed()}
