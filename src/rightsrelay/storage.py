from __future__ import annotations

import os
from pathlib import Path

from genblaze_core import KeyStrategy, ObjectStorageSink
from genblaze_s3 import S3StorageBackend

from .config import Settings

STATE_KEY = "rightsrelay/state/index.sqlite3"


def create_b2_backend(settings: Settings) -> S3StorageBackend:
    """Create a bucket-scoped backend without returning or logging secrets."""

    if not settings.b2_enabled:
        raise RuntimeError("Backblaze B2 is not configured")

    os.environ["B2_KEY_ID"] = settings.b2_key_id or ""
    os.environ["B2_APP_KEY"] = settings.b2_app_key or ""
    return S3StorageBackend.for_backblaze(
        settings.b2_bucket or "",
        region=settings.b2_region,
        public_url_base=settings.b2_public_url_base,
        auto_lifecycle=False,
    )


def create_b2_sink(settings: Settings) -> ObjectStorageSink | None:
    """Create one run-scoped B2 sink without exposing credential values."""

    if not settings.b2_enabled:
        return None

    backend = create_b2_backend(settings)
    return ObjectStorageSink(
        backend,
        prefix="rightsrelay",
        key_strategy=KeyStrategy.CONTENT_ADDRESSABLE,
    )


def restore_database_from_b2(settings: Settings, database_path: Path) -> bool:
    """Atomically restore the private SQLite reverse index when it exists."""

    if not settings.b2_enabled:
        return False
    backend = create_b2_backend(settings)
    try:
        if not backend.exists(STATE_KEY):
            return False
        restored = database_path.with_suffix(".restore")
        restored.write_bytes(backend.get(STATE_KEY))
        os.replace(restored, database_path)
        return True
    finally:
        backend.close()


def persist_database_to_b2(settings: Settings, database_path: Path) -> None:
    """Persist the current reverse index to a private, stable B2 object."""

    if not settings.b2_enabled:
        return
    backend = create_b2_backend(settings)
    try:
        backend.put(
            STATE_KEY,
            database_path.read_bytes(),
            content_type="application/vnd.sqlite3",
            extra_args={"CacheControl": "no-store"},
        )
    finally:
        backend.close()


def read_b2_url(settings: Settings, durable_url: str) -> bytes:
    """Read a private object identified by its credential-free durable URL."""

    backend = create_b2_backend(settings)
    try:
        key = backend.key_from_url(durable_url)
        if key is None:
            raise FileNotFoundError("asset URL does not belong to the configured B2 bucket")
        return backend.get(key)
    finally:
        backend.close()


def read_b2_manifest(settings: Settings, run_id: str) -> bytes:
    backend = create_b2_backend(settings)
    try:
        return backend.get(f"rightsrelay/manifests/{run_id}.json")
    finally:
        backend.close()


def write_bytes_content_addressed(directory: Path, data: bytes, suffix: str) -> Path:
    import hashlib

    digest = hashlib.sha256(data).hexdigest()
    path = directory / f"{digest}{suffix}"
    if not path.exists():
        path.write_bytes(data)
    return path
