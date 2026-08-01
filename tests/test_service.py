from __future__ import annotations

import json
import os
import wave
from pathlib import Path

import pytest

from rightsrelay.config import Settings
from rightsrelay.models import CampaignCreate
from rightsrelay.service import RightsRelayService


def model_paths() -> tuple[Path, Path]:
    model_dir = Path(
        os.environ.get(
            "RIGHTSRELAY_TEST_MODEL_DIR",
            r"F:\CodexLab\caches\piper\en_US-libritts_r-medium",
        )
    )
    return (
        model_dir / "en_US-libritts_r-medium.onnx",
        model_dir / "en_US-libritts_r-medium.onnx.json",
    )


@pytest.fixture(scope="module")
def voice_files() -> tuple[Path, Path]:
    model, config = model_paths()
    if not model.is_file() or not config.is_file():
        pytest.skip("Piper test voice is not installed")
    return model, config


def make_service(tmp_path: Path, voice_files: tuple[Path, Path]) -> RightsRelayService:
    model, config = voice_files
    settings = Settings(
        data_dir=tmp_path,
        voice_model_path=model,
        voice_config_path=config,
        max_script_chars=1500,
    )
    return RightsRelayService(settings)


def test_real_generation_and_manifest_verify(tmp_path: Path, voice_files) -> None:
    service = make_service(tmp_path, voice_files)
    campaign = service.create_campaign(
        CampaignCreate(
            title="Launch narration",
            script="This derivative was generated locally and its bytes are verifiable.",
            voice_id="atlas",
        )
    )

    audio = Path(campaign.audio_path)
    assert audio.is_file()
    with wave.open(str(audio), "rb") as wav:
        assert wav.getframerate() == 22050
        assert wav.getnframes() > 1000

    verification = service.verify_campaign(campaign.id)
    assert verification["verified"] is True

    manifest = json.loads(Path(campaign.manifest_path).read_text(encoding="utf-8"))
    assert manifest["run"]["metadata"]["voice_profile"] == "atlas"
    assert manifest["run"]["steps"][0]["provider"] == "piper-local"
    assert manifest["run"]["steps"][0]["model"] == "en_US-libritts_r-medium"


def test_revocation_regenerates_and_preserves_history(tmp_path: Path, voice_files) -> None:
    service = make_service(tmp_path, voice_files)
    first = service.create_campaign(
        CampaignCreate(
            title="Rights window", script="Replace this voice when revoked.", voice_id="atlas"
        )
    )
    regenerated = service.revoke_and_regenerate("atlas", "nova")

    assert len(regenerated) == 1
    second = regenerated[0]
    assert second.id == first.id
    assert second.voice_id == "nova"
    assert second.revision == 2
    assert second.current_manifest_hash != first.current_manifest_hash
    assert service.verify_campaign(second.id)["verified"] is True

    history = service.db.history(first.id)
    assert [item.revision for item in history] == [2, 1]
    assert history[0].reason == "voice-revoked:atlas"
    second_manifest = json.loads(Path(second.manifest_path).read_text(encoding="utf-8"))
    assert second_manifest["run"]["metadata"]["replaces_run_id"] == first.current_run_id
    assert (
        second_manifest["run"]["metadata"]["replaces_manifest_hash"] == first.current_manifest_hash
    )


def test_failed_replacement_does_not_commit_revocation(
    tmp_path: Path, voice_files, monkeypatch
) -> None:
    service = make_service(tmp_path, voice_files)
    first = service.create_campaign(
        CampaignCreate(
            title="Atomic revocation",
            script="Keep the current revision when replacement generation fails.",
            voice_id="atlas",
        )
    )

    def fail_render(**_kwargs):
        raise RuntimeError("simulated provider failure")

    monkeypatch.setattr(service, "_render", fail_render)
    with pytest.raises(RuntimeError, match="simulated provider failure"):
        service.revoke_and_regenerate("atlas", "nova")

    atlas = service.db.get_voice("atlas")
    assert atlas is not None
    assert atlas.status == "active"
    current = service.db.get_campaign(first.id)
    assert current is not None
    assert current.revision == 1
    assert current.voice_id == "atlas"


def test_tamper_detection(tmp_path: Path, voice_files) -> None:
    service = make_service(tmp_path, voice_files)
    campaign = service.create_campaign(
        CampaignCreate(
            title="Tamper check", script="This file should fail after mutation.", voice_id="nova"
        )
    )
    path = Path(campaign.audio_path)
    path.write_bytes(path.read_bytes() + b"tampered")
    assert service.verify_campaign(campaign.id)["verified"] is False


def test_manifest_tampering_invalidates_canonical_proof(tmp_path: Path, voice_files) -> None:
    service = make_service(tmp_path, voice_files)
    campaign = service.create_campaign(
        CampaignCreate(
            title="Manifest check",
            script="Changing provenance without changing audio must still fail.",
            voice_id="nova",
        )
    )
    path = Path(campaign.manifest_path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["run"]["metadata"]["trigger"] = "tampered-trigger"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    verification = service.verify_campaign(campaign.id)
    assert verification["manifest_verified"] is False
    assert verification["verified"] is False


def test_public_proof_withholds_prompt_and_internal_paths(tmp_path: Path, voice_files) -> None:
    service = make_service(tmp_path, voice_files)
    private_script = "This exact campaign sentence must not appear in the public proof."
    campaign = service.create_campaign(
        CampaignCreate(title="Redaction check", script=private_script, voice_id="atlas")
    )

    proof = service.public_proof(campaign.id)
    serialized = json.dumps(proof)
    assert private_script not in serialized
    assert "audio_path" not in proof
    assert "manifest_path" not in proof
    assert "audio_url" not in proof
    assert proof["prompt"].startswith("withheld")
    assert proof["manifest_verified"] is True


def test_demo_seed_is_idempotent_and_shows_replacement(tmp_path: Path, voice_files) -> None:
    service = make_service(tmp_path, voice_files)
    seeded = service.seed_demo()

    assert seeded.voice_id == "nova"
    assert seeded.revision == 2
    assert seeded.status == "regenerated"
    assert len(service.campaigns()) == 1
    assert len(service.db.history(seeded.id)) == 2

    again = service.seed_demo()
    assert again.id == seeded.id
    assert len(service.campaigns()) == 1
