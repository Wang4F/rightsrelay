from __future__ import annotations

from pathlib import Path

from rightsrelay import storage
from rightsrelay.config import Settings


class FakeBackend:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.closed = False

    def exists(self, key: str) -> bool:
        return key in self.objects

    def put(self, key: str, data: bytes, **_kwargs) -> str:
        self.objects[key] = bytes(data)
        return key

    def get(self, key: str) -> bytes:
        return self.objects[key]

    def close(self) -> None:
        self.closed = True


def test_private_b2_index_snapshot_round_trip(tmp_path: Path, monkeypatch) -> None:
    backend = FakeBackend()
    monkeypatch.setattr(storage, "create_b2_backend", lambda _settings: backend)
    settings = Settings(
        data_dir=tmp_path,
        b2_key_id="scoped-key-id",
        b2_app_key="scoped-app-key",
        b2_bucket="private-demo-bucket",
    )
    database = tmp_path / "rightsrelay.sqlite3"
    database.write_bytes(b"sqlite-state-snapshot")

    storage.persist_database_to_b2(settings, database)
    database.unlink()
    restored = storage.restore_database_from_b2(settings, database)

    assert restored is True
    assert database.read_bytes() == b"sqlite-state-snapshot"
    assert storage.STATE_KEY in backend.objects
