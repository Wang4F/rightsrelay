from __future__ import annotations

import hashlib
from pathlib import Path
from threading import RLock
from uuid import uuid4

from genblaze_core import Asset, Manifest, Modality, Pipeline, PromptVisibility

from .config import Settings
from .database import Database
from .models import CampaignCreate, CampaignRecord, VoiceProfile, utc_now_iso
from .provider import PiperTTSProvider
from .storage import (
    create_b2_sink,
    persist_database_to_b2,
    read_b2_manifest,
    read_b2_url,
    restore_database_from_b2,
    write_bytes_content_addressed,
)


class RightsRelayService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.settings.ensure_directories()
        self._mutation_lock = RLock()
        database_path = settings.data_dir / "rightsrelay.sqlite3"
        restore_database_from_b2(settings, database_path)
        self.db = Database(database_path)
        self.provider = PiperTTSProvider(
            settings.voice_model_path,
            settings.voice_config_path,
            settings.data_dir / "audio",
        )

    def voices(self) -> list[VoiceProfile]:
        return self.db.list_voices()

    def campaigns(self) -> list[CampaignRecord]:
        return self.db.list_campaigns()

    def seed_demo(self) -> CampaignRecord:
        """Create a reproducible before/after example on an empty deployment."""

        with self._mutation_lock:
            existing = self.campaigns()
            if existing:
                seeded = next(
                    (item for item in existing if item.title == "Consent-aware launch narration"),
                    existing[0],
                )
                atlas = self.db.get_voice("atlas")
                if seeded.voice_id == "atlas" and atlas and atlas.status == "active":
                    regenerated = self.revoke_and_regenerate("atlas", "nova")
                    return regenerated[0] if regenerated else seeded
                return seeded

            # A Render free instance has an ephemeral filesystem. Restoring
            # the known baseline first makes a cold-start seed deterministic.
            self.restore_voice("atlas")
            self.restore_voice("nova")
            initial = self.create_campaign(
                CampaignCreate(
                    title="Consent-aware launch narration",
                    script=(
                        "RightsRelay keeps every synthetic voice derivative linked to its "
                        "source and voice profile, then regenerates affected media when that "
                        "profile is revoked."
                    ),
                    voice_id="atlas",
                )
            )
            regenerated = self.revoke_and_regenerate("atlas", "nova")
            return regenerated[0] if regenerated else initial

    def create_campaign(self, payload: CampaignCreate) -> CampaignRecord:
        with self._mutation_lock:
            if len(payload.script) > self.settings.max_script_chars:
                raise ValueError(f"script exceeds {self.settings.max_script_chars} characters")
            if len(self.campaigns()) >= self.settings.max_campaigns:
                raise ValueError("demo campaign limit reached")
            voice = self._require_active_voice(payload.voice_id)
            campaign_id = uuid4().hex[:12]
            record = self._render(
                campaign_id=campaign_id,
                title=payload.title,
                script=payload.script,
                voice=voice,
                valid_until=payload.operational_valid_until,
                revision=1,
                reason="initial-generation",
                previous=None,
            )
            self._persist_state()
            return record

    def revoke_and_regenerate(self, voice_id: str, replacement_id: str) -> list[CampaignRecord]:
        with self._mutation_lock:
            if voice_id == replacement_id:
                raise ValueError("replacement voice must be different")
            voice = self.db.get_voice(voice_id)
            replacement = self._require_active_voice(replacement_id)
            if voice is None:
                raise ValueError("unknown voice profile")

            affected = self.db.campaigns_for_voice(voice_id)
            reason = f"voice-revoked:{voice_id}"
            regenerated: list[CampaignRecord] = []
            for current in affected:
                regenerated.append(
                    self._render(
                        campaign_id=current.id,
                        title=current.title,
                        script=current.script,
                        voice=replacement,
                        valid_until=current.operational_valid_until,
                        revision=current.revision + 1,
                        reason=reason,
                        previous=current,
                        save=False,
                    )
                )
            self.db.apply_revocation(
                voice_id,
                replacement_id,
                [(record, reason) for record in regenerated],
            )
            self._persist_state()
            return regenerated

    def restore_voice(self, voice_id: str) -> VoiceProfile:
        with self._mutation_lock:
            if self.db.get_voice(voice_id) is None:
                raise ValueError("unknown voice profile")
            self.db.set_voice_status(voice_id, "active", None)
            restored = self.db.get_voice(voice_id)
            assert restored is not None
            self._persist_state()
            return restored

    def verify_campaign(self, campaign_id: str) -> dict[str, object]:
        campaign = self.db.get_campaign(campaign_id)
        if campaign is None:
            raise ValueError("unknown campaign")
        raw_manifest = self._manifest_bytes(campaign)
        manifest = Manifest.model_validate_json(raw_manifest)
        manifest_valid = manifest.verify()
        hash_matches_index = manifest.canonical_hash == campaign.current_manifest_hash
        run_matches_index = manifest.run.run_id == campaign.current_run_id
        declared = manifest.run.steps[0].assets[0].sha256
        actual = hashlib.sha256(self.audio_bytes(campaign)).hexdigest()
        return {
            "campaign_id": campaign_id,
            "manifest_hash": campaign.current_manifest_hash,
            "declared_audio_sha256": declared,
            "actual_audio_sha256": actual,
            "manifest_verified": manifest_valid,
            "verified": (
                manifest_valid and hash_matches_index and run_matches_index and declared == actual
            ),
        }

    def public_proof(self, campaign_id: str) -> dict[str, object]:
        """Return provenance facts without exposing the prompt or local paths."""

        campaign = self.db.get_campaign(campaign_id)
        if campaign is None:
            raise ValueError("unknown campaign")
        manifest = Manifest.model_validate_json(self._manifest_bytes(campaign))
        step = manifest.run.steps[0]
        asset = step.assets[0]
        metadata = manifest.run.metadata
        return {
            "schema_version": manifest.schema_version,
            "campaign_id": campaign.id,
            "revision": campaign.revision,
            "run_id": manifest.run.run_id,
            "canonical_manifest_hash": manifest.canonical_hash,
            "manifest_verified": manifest.verify(),
            "provider": step.provider,
            "model": step.model,
            "voice_profile": metadata.get("voice_profile"),
            "trigger": metadata.get("trigger"),
            "source_manifest_hash": metadata.get("source_manifest_hash"),
            "replaces_run_id": metadata.get("replaces_run_id"),
            "replaces_manifest_hash": metadata.get("replaces_manifest_hash"),
            "audio_sha256": asset.sha256,
            "audio_size_bytes": asset.size_bytes,
            "audio_duration_seconds": asset.duration,
            "prompt": "withheld; full canonical manifest remains in private B2 storage",
        }

    def audio_bytes(self, campaign: CampaignRecord) -> bytes:
        audio_path = Path(campaign.audio_path)
        if audio_path.is_file():
            return audio_path.read_bytes()
        if self.settings.b2_enabled:
            return read_b2_url(self.settings, campaign.audio_url)
        raise FileNotFoundError("media unavailable")

    def _manifest_bytes(self, campaign: CampaignRecord) -> bytes:
        manifest_path = Path(campaign.manifest_path)
        if manifest_path.is_file():
            return manifest_path.read_bytes()
        if self.settings.b2_enabled:
            return read_b2_manifest(self.settings, campaign.current_run_id)
        raise FileNotFoundError("manifest unavailable")

    def _persist_state(self) -> None:
        persist_database_to_b2(self.settings, self.db.path)

    def _require_active_voice(self, voice_id: str) -> VoiceProfile:
        voice = self.db.get_voice(voice_id)
        if voice is None:
            raise ValueError("unknown voice profile")
        if voice.status != "active":
            raise ValueError("voice profile is revoked")
        return voice

    def _render(
        self,
        *,
        campaign_id: str,
        title: str,
        script: str,
        voice: VoiceProfile,
        valid_until: str | None,
        revision: int,
        reason: str,
        previous: CampaignRecord | None,
        save: bool = True,
    ) -> CampaignRecord:
        script_bytes = script.encode("utf-8")
        script_path = write_bytes_content_addressed(
            self.settings.data_dir / "scripts", script_bytes, ".txt"
        )
        script_asset = Asset(
            url=script_path.resolve().as_uri(),
            media_type="text/plain",
            sha256=hashlib.sha256(script_bytes).hexdigest(),
            size_bytes=len(script_bytes),
            metadata={"role": "source-script", "campaign_id": campaign_id},
        )

        # Persist the source independently so B2 holds both source and derivative.
        ingest_sink = create_b2_sink(self.settings)
        try:
            ingest_result = Pipeline.ingest(
                assets=[script_asset],
                source="rightsrelay-script",
                source_metadata={"campaign_id": campaign_id, "revision": revision},
                sink=ingest_sink,
                name=f"script-{campaign_id}-r{revision}",
                tenant_id="rightsrelay-demo",
            )
        finally:
            if ingest_sink is not None:
                ingest_sink.close()

        sink = create_b2_sink(self.settings)
        metadata = {
            "campaign_id": campaign_id,
            "revision": revision,
            "voice_profile": voice.id,
            "operational_valid_until": valid_until,
            "trigger": reason,
            "source_manifest_hash": ingest_result.manifest.canonical_hash,
        }
        if previous is not None:
            metadata.update(
                {
                    "replaces_run_id": previous.current_run_id,
                    "replaces_manifest_hash": previous.current_manifest_hash,
                }
            )

        result = (
            Pipeline(
                f"rightsrelay-{campaign_id}-r{revision}",
                tenant_id="rightsrelay-demo",
                project_id="backblaze-genmedia-2026",
            )
            .metadata(**metadata)
            .step(
                self.provider,
                model="en_US-libritts_r-medium",
                prompt=script,
                modality=Modality.AUDIO,
                external_inputs=[script_asset],
                prompt_visibility=PromptVisibility.PRIVATE,
                metadata=metadata,
                speaker_id=voice.speaker_id,
                length_scale=1.0,
            )
            .run(sink=sink, timeout=120, raise_on_failure=True)
        )
        if not result.manifest.verify():
            raise RuntimeError("Genblaze manifest verification failed")

        asset = result.run.steps[0].assets[0]
        local_filename = str(asset.metadata["local_filename"])
        audio_path = (self.settings.data_dir / "audio" / local_filename).resolve()
        manifest_path = (
            self.settings.data_dir / "manifests" / f"{result.run.run_id}.json"
        ).resolve()
        manifest_path.write_text(result.manifest.to_canonical_json(), encoding="utf-8")

        now = utc_now_iso()
        record = CampaignRecord(
            id=campaign_id,
            title=title,
            script=script,
            voice_id=voice.id,
            status="regenerated" if previous else "active",
            operational_valid_until=valid_until,
            revision=revision,
            current_run_id=result.run.run_id,
            current_manifest_hash=result.manifest.canonical_hash or "",
            audio_path=str(audio_path),
            audio_url=asset.url,
            manifest_path=str(manifest_path),
            created_at=previous.created_at if previous else now,
            updated_at=now,
        )
        if save:
            self.db.save_campaign(record, reason)
        return record
