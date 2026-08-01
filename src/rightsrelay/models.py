from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class VoiceProfile(BaseModel):
    id: str
    label: str
    speaker_id: int
    status: Literal["active", "revoked"] = "active"
    replacement_id: str | None = None
    revoked_at: str | None = None


VOICE_PROFILES: dict[str, VoiceProfile] = {
    "atlas": VoiceProfile(id="atlas", label="Atlas", speaker_id=0),
    "nova": VoiceProfile(id="nova", label="Nova", speaker_id=1),
}


class CampaignCreate(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    script: str = Field(min_length=1, max_length=1500)
    voice_id: str = "atlas"
    operational_valid_until: str | None = None

    @field_validator("title", "script")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class RevokeRequest(BaseModel):
    replacement_id: str


class CampaignRecord(BaseModel):
    id: str
    title: str
    script: str
    voice_id: str
    status: str
    operational_valid_until: str | None
    revision: int
    current_run_id: str
    current_manifest_hash: str
    audio_path: str
    audio_url: str
    manifest_path: str
    created_at: str
    updated_at: str


class HistoryRecord(BaseModel):
    campaign_id: str
    revision: int
    voice_id: str
    reason: str
    run_id: str
    manifest_hash: str
    audio_path: str
    audio_url: str
    manifest_path: str
    created_at: str
