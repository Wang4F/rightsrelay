from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import RLock

from .models import VOICE_PROFILES, CampaignRecord, HistoryRecord, VoiceProfile, utc_now_iso


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._lock, self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS voice_profiles (
                    id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    speaker_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    replacement_id TEXT,
                    revoked_at TEXT
                );
                CREATE TABLE IF NOT EXISTS campaigns (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    script TEXT NOT NULL,
                    voice_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    operational_valid_until TEXT,
                    revision INTEGER NOT NULL,
                    current_run_id TEXT NOT NULL,
                    current_manifest_hash TEXT NOT NULL,
                    audio_path TEXT NOT NULL,
                    audio_url TEXT NOT NULL,
                    manifest_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS campaign_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    voice_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    manifest_hash TEXT NOT NULL,
                    audio_path TEXT NOT NULL,
                    audio_url TEXT NOT NULL,
                    manifest_path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            for profile in VOICE_PROFILES.values():
                conn.execute(
                    """
                    INSERT OR IGNORE INTO voice_profiles
                    (id, label, speaker_id, status, replacement_id, revoked_at)
                    VALUES (?, ?, ?, ?, NULL, NULL)
                    """,
                    (profile.id, profile.label, profile.speaker_id, profile.status),
                )

    def list_voices(self) -> list[VoiceProfile]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM voice_profiles ORDER BY id").fetchall()
        return [VoiceProfile(**dict(row)) for row in rows]

    def get_voice(self, voice_id: str) -> VoiceProfile | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM voice_profiles WHERE id=?", (voice_id,)).fetchone()
        return VoiceProfile(**dict(row)) if row else None

    def set_voice_status(
        self, voice_id: str, status: str, replacement_id: str | None = None
    ) -> None:
        revoked_at = utc_now_iso() if status == "revoked" else None
        with self._lock, self.connect() as conn:
            conn.execute(
                """
                UPDATE voice_profiles
                SET status=?, replacement_id=?, revoked_at=?
                WHERE id=?
                """,
                (status, replacement_id, revoked_at, voice_id),
            )

    @staticmethod
    def _save_campaign(conn: sqlite3.Connection, campaign: CampaignRecord, reason: str) -> None:
        conn.execute(
            """
                INSERT INTO campaigns VALUES
                (:id,:title,:script,:voice_id,:status,:operational_valid_until,:revision,
                 :current_run_id,:current_manifest_hash,:audio_path,:audio_url,:manifest_path,
                 :created_at,:updated_at)
                ON CONFLICT(id) DO UPDATE SET
                  title=excluded.title, script=excluded.script, voice_id=excluded.voice_id,
                  status=excluded.status,
                  operational_valid_until=excluded.operational_valid_until,
                  revision=excluded.revision, current_run_id=excluded.current_run_id,
                  current_manifest_hash=excluded.current_manifest_hash,
                  audio_path=excluded.audio_path, audio_url=excluded.audio_url,
                  manifest_path=excluded.manifest_path, updated_at=excluded.updated_at
                """,
            campaign.model_dump(),
        )
        conn.execute(
            """
                INSERT INTO campaign_history
                (campaign_id,revision,voice_id,reason,run_id,manifest_hash,audio_path,
                 audio_url,manifest_path,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
            (
                campaign.id,
                campaign.revision,
                campaign.voice_id,
                reason,
                campaign.current_run_id,
                campaign.current_manifest_hash,
                campaign.audio_path,
                campaign.audio_url,
                campaign.manifest_path,
                campaign.updated_at,
            ),
        )

    def save_campaign(self, campaign: CampaignRecord, reason: str) -> None:
        with self._lock, self.connect() as conn:
            self._save_campaign(conn, campaign, reason)

    def apply_revocation(
        self,
        voice_id: str,
        replacement_id: str,
        replacements: list[tuple[CampaignRecord, str]],
    ) -> None:
        """Commit the voice decision and every replacement in one transaction."""

        revoked_at = utc_now_iso()
        with self._lock, self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                UPDATE voice_profiles
                SET status='revoked', replacement_id=?, revoked_at=?
                WHERE id=?
                """,
                (replacement_id, revoked_at, voice_id),
            )
            for campaign, reason in replacements:
                self._save_campaign(conn, campaign, reason)

    def get_campaign(self, campaign_id: str) -> CampaignRecord | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
        return CampaignRecord(**dict(row)) if row else None

    def list_campaigns(self) -> list[CampaignRecord]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM campaigns ORDER BY updated_at DESC").fetchall()
        return [CampaignRecord(**dict(row)) for row in rows]

    def campaigns_for_voice(self, voice_id: str) -> list[CampaignRecord]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM campaigns WHERE voice_id=? ORDER BY updated_at", (voice_id,)
            ).fetchall()
        return [CampaignRecord(**dict(row)) for row in rows]

    def history(self, campaign_id: str) -> list[HistoryRecord]:
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT campaign_id,revision,voice_id,reason,run_id,manifest_hash,
                          audio_path,audio_url,manifest_path,created_at
                   FROM campaign_history WHERE campaign_id=? ORDER BY revision DESC""",
                (campaign_id,),
            ).fetchall()
        return [HistoryRecord(**dict(row)) for row in rows]
