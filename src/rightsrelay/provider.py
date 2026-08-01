from __future__ import annotations

import hashlib
import threading
import wave
from pathlib import Path

from genblaze_core import Asset, Modality, ProviderCapabilities, SyncProvider
from genblaze_core.models.step import Step
from genblaze_core.runnable.config import RunnableConfig
from piper.config import SynthesisConfig
from piper.voice import PiperVoice


class PiperTTSProvider(SyncProvider):
    """A real, offline neural TTS provider exposed through Genblaze."""

    name = "piper-local"
    capabilities = ProviderCapabilities(
        supported_modalities=[Modality.AUDIO],
        supported_inputs=["text"],
        accepts_chain_input=True,
        output_formats=["audio/wav"],
        models=["en_US-libritts_r-medium"],
    )

    def __init__(self, model_path: Path, config_path: Path, output_dir: Path) -> None:
        super().__init__()
        self._model_path = model_path
        self._config_path = config_path
        self._output_dir = output_dir
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._voice: PiperVoice | None = None
        self._voice_lock = threading.Lock()
        self._synthesis_lock = threading.Lock()

    def _get_voice(self) -> PiperVoice:
        if self._voice is None:
            with self._voice_lock:
                if self._voice is None:
                    if not self._model_path.is_file() or not self._config_path.is_file():
                        raise FileNotFoundError(
                            "Piper voice files are missing. Run the documented voice download command."
                        )
                    self._voice = PiperVoice.load(
                        self._model_path,
                        config_path=self._config_path,
                    )
        return self._voice

    def generate(self, step: Step, config: RunnableConfig | None = None) -> Step:
        text = (step.prompt or "").strip()
        if not text:
            raise ValueError("TTS prompt must not be empty")

        speaker_id = int(step.params.get("speaker_id", 0))
        length_scale = float(step.params.get("length_scale", 1.0))
        output_path = (self._output_dir / f"{step.step_id}.wav").resolve()

        synthesis = SynthesisConfig(
            speaker_id=speaker_id,
            length_scale=length_scale,
            normalize_audio=True,
        )
        with self._synthesis_lock, wave.open(str(output_path), "wb") as wav_file:
            self._get_voice().synthesize_wav(text, wav_file, synthesis)

        raw = output_path.read_bytes()
        with wave.open(str(output_path), "rb") as wav_file:
            duration = wav_file.getnframes() / float(wav_file.getframerate())

        step.assets.append(
            Asset(
                url=output_path.as_uri(),
                media_type="audio/wav",
                sha256=hashlib.sha256(raw).hexdigest(),
                size_bytes=len(raw),
                duration=duration,
                metadata={
                    "role": "voice-derivative",
                    "local_filename": output_path.name,
                    "speaker_id": speaker_id,
                    "engine": "piper-tts",
                },
            )
        )
        step.cost_usd = 0.0
        return step
