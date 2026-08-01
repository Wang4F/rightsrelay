from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Secret values are never rendered or logged."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    data_dir: Path = Field(Path("data"), alias="RIGHTSRELAY_DATA_DIR")
    voice_model_path: Path = Field(
        Path(".models/en_US-libritts_r-medium.onnx"),
        alias="RIGHTSRELAY_VOICE_MODEL_PATH",
    )
    voice_config_path: Path = Field(
        Path(".models/en_US-libritts_r-medium.onnx.json"),
        alias="RIGHTSRELAY_VOICE_CONFIG_PATH",
    )
    max_script_chars: int = Field(1500, alias="RIGHTSRELAY_MAX_SCRIPT_CHARS")
    max_campaigns: int = Field(24, alias="RIGHTSRELAY_MAX_CAMPAIGNS")
    mutation_limit: int = Field(12, alias="RIGHTSRELAY_MUTATION_LIMIT")
    mutation_window_seconds: int = Field(600, alias="RIGHTSRELAY_MUTATION_WINDOW_SECONDS")
    seed_demo: bool = Field(False, alias="RIGHTSRELAY_SEED_DEMO")

    b2_key_id: str | None = Field(None, alias="B2_KEY_ID", repr=False)
    b2_app_key: str | None = Field(None, alias="B2_APP_KEY", repr=False)
    b2_bucket: str | None = Field(None, alias="B2_BUCKET")
    b2_region: str = Field("us-west-004", alias="B2_REGION")
    b2_public_url_base: str | None = Field(None, alias="B2_PUBLIC_URL_BASE")
    require_b2: bool = Field(False, alias="RIGHTSRELAY_REQUIRE_B2")

    @model_validator(mode="after")
    def normalize_paths(self) -> Settings:
        self.data_dir = self.data_dir.expanduser().resolve()
        self.voice_model_path = self.voice_model_path.expanduser().resolve()
        self.voice_config_path = self.voice_config_path.expanduser().resolve()
        return self

    @property
    def b2_enabled(self) -> bool:
        return bool(self.b2_key_id and self.b2_app_key and self.b2_bucket)

    def ensure_directories(self) -> None:
        for child in ("audio", "scripts", "manifests"):
            (self.data_dir / child).mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
