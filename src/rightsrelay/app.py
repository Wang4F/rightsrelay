from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock
from time import monotonic

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from . import __version__
from .config import get_settings
from .models import CampaignCreate, RevokeRequest
from .service import RightsRelayService

PACKAGE_DIR = Path(__file__).resolve().parent
settings = get_settings()
service = RightsRelayService(settings)
mutation_events: dict[str, deque[float]] = defaultdict(deque)
mutation_events_lock = Lock()


def campaign_view(campaign) -> dict[str, object]:
    return {
        "id": campaign.id,
        "title": campaign.title,
        "voice_id": campaign.voice_id,
        "status": campaign.status,
        "operational_valid_until": campaign.operational_valid_until,
        "revision": campaign.revision,
        "current_run_id": campaign.current_run_id,
        "current_manifest_hash": campaign.current_manifest_hash,
        "created_at": campaign.created_at,
        "updated_at": campaign.updated_at,
    }


def enforce_mutation_limit(request: Request) -> None:
    if settings.mutation_limit <= 0:
        return
    client = request.client.host if request.client else "unknown"
    now = monotonic()
    cutoff = now - settings.mutation_window_seconds
    with mutation_events_lock:
        events = mutation_events[client]
        while events and events[0] < cutoff:
            events.popleft()
        if len(events) >= settings.mutation_limit:
            raise HTTPException(
                status_code=429,
                detail="demo mutation limit reached; retry after the window resets",
            )
        events.append(now)


async def run_demo_seed(application: FastAPI) -> None:
    application.state.seed_status = "running"
    try:
        await asyncio.to_thread(service.seed_demo)
    except Exception as exc:  # noqa: BLE001 - report only the safe exception class
        application.state.seed_status = "error"
        application.state.seed_error = type(exc).__name__
    else:
        application.state.seed_status = "ready"


@asynccontextmanager
async def lifespan(application: FastAPI):
    seed_task = None
    if settings.seed_demo:
        application.state.seed_status = "pending"
        seed_task = asyncio.create_task(run_demo_seed(application))
    else:
        application.state.seed_status = "disabled"
    yield
    if seed_task and not seed_task.done():
        seed_task.cancel()


app = FastAPI(title="RightsRelay", version=__version__, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=PACKAGE_DIR / "templates")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "version": __version__,
        "b2_configured": settings.b2_enabled,
        "voice_model_ready": settings.voice_model_path.is_file(),
        "demo_seeded": bool(service.campaigns()),
        "seed_status": getattr(app.state, "seed_status", "not-started"),
    }


@app.get("/ready")
def ready():
    problems = []
    if not settings.voice_model_path.is_file() or not settings.voice_config_path.is_file():
        problems.append("voice-model-missing")
    if settings.require_b2 and not settings.b2_enabled:
        problems.append("b2-required")
    if getattr(app.state, "seed_status", None) == "error":
        problems.append("demo-seed-failed")
    body = {
        "status": "ready" if not problems else "not-ready",
        "problems": problems,
        "b2_configured": settings.b2_enabled,
        "seed_status": getattr(app.state, "seed_status", "not-started"),
    }
    return JSONResponse(body, status_code=200 if not problems else 503)


@app.get("/api/state")
def state() -> dict[str, object]:
    campaigns = service.campaigns()
    return {
        "voices": [voice.model_dump() for voice in service.voices()],
        "campaigns": [campaign_view(campaign) for campaign in campaigns],
        "b2_configured": settings.b2_enabled,
        "model": {
            "id": "en_US-libritts_r-medium",
            "engine": "Piper TTS 1.6.0",
            "dataset_license": "CC BY 4.0",
            "genblaze": "genblaze-core 0.3.8",
        },
    }


@app.post("/api/campaigns", status_code=201)
def create_campaign(payload: CampaignCreate, request: Request):
    enforce_mutation_limit(request)
    try:
        return campaign_view(service.create_campaign(payload))
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/voices/{voice_id}/revoke")
def revoke_voice(voice_id: str, payload: RevokeRequest, request: Request):
    enforce_mutation_limit(request)
    try:
        regenerated = service.revoke_and_regenerate(voice_id, payload.replacement_id)
        return {
            "revoked": voice_id,
            "replacement": payload.replacement_id,
            "regenerated": [campaign_view(record) for record in regenerated],
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/voices/{voice_id}/restore")
def restore_voice(voice_id: str, request: Request):
    enforce_mutation_limit(request)
    try:
        return service.restore_voice(voice_id).model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/campaigns/{campaign_id}/history")
def history(campaign_id: str):
    if service.db.get_campaign(campaign_id) is None:
        raise HTTPException(status_code=404, detail="unknown campaign")
    return [
        {
            "campaign_id": item.campaign_id,
            "revision": item.revision,
            "voice_id": item.voice_id,
            "reason": item.reason,
            "run_id": item.run_id,
            "manifest_hash": item.manifest_hash,
            "created_at": item.created_at,
        }
        for item in service.db.history(campaign_id)
    ]


@app.get("/api/campaigns/{campaign_id}/verify")
def verify(campaign_id: str):
    try:
        return service.verify_campaign(campaign_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/media/{campaign_id}")
def media(campaign_id: str):
    campaign = service.db.get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="unknown campaign")
    local = Path(campaign.audio_path)
    if local.is_file():
        return FileResponse(local, media_type="audio/wav", filename=f"{campaign_id}.wav")
    try:
        return Response(
            content=service.audio_bytes(campaign),
            media_type="audio/wav",
            headers={"Cache-Control": "private, max-age=300"},
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="media unavailable") from exc


@app.get("/proofs/{campaign_id}")
def proof(campaign_id: str):
    try:
        return service.public_proof(campaign_id)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
