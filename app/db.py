"""SQLite persistence for gallery entries and idempotency records."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Settings

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS gallery (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id TEXT NOT NULL,
    person_id TEXT NOT NULL,
    name TEXT NOT NULL,
    image_sha256 TEXT NOT NULL,
    image_bytes BLOB NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (group_id, person_id)
);
CREATE INDEX IF NOT EXISTS idx_gallery_group ON gallery(group_id);

CREATE TABLE IF NOT EXISTS idempotency (
    key TEXT PRIMARY KEY,
    fingerprint TEXT NOT NULL,
    status INTEGER NOT NULL,
    data_json TEXT NOT NULL,
    created_at REAL NOT NULL
);
"""


class DuplicatePersonError(Exception):
    pass


class Repository:
    def __init__(self, settings: Settings) -> None:
        self.path = Path(settings.db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._schema_lock = threading.Lock()
        self.init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=20)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_schema(self) -> None:
        with self._schema_lock:
            conn = self.connect()
            try:
                conn.executescript(SCHEMA)
                conn.commit()
            finally:
                conn.close()

    def ping(self) -> bool:
        conn = None
        try:
            conn = self.connect()
            return conn.execute("SELECT 1").fetchone()[0] == 1
        except sqlite3.Error:
            return False
        finally:
            if conn is not None:
                conn.close()

    # ------------------------------------------------------------------ gallery
    def add_person(
        self,
        *,
        group_id: str,
        person_id: str,
        name: str,
        image_sha256: str,
        image_bytes: bytes,
    ) -> dict[str, Any]:
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        try:
            with self.connect() as conn:
                cursor = conn.execute(
                    "INSERT INTO gallery "
                    "(group_id, person_id, name, image_sha256, image_bytes, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (group_id, person_id, name, image_sha256, sqlite3.Binary(image_bytes), created_at),
                )
                record_id = cursor.lastrowid
        except sqlite3.IntegrityError as exc:
            raise DuplicatePersonError(f"{group_id}/{person_id} already exists") from exc
        return {
            "id": int(record_id),
            "group_id": group_id,
            "person_id": person_id,
            "name": name,
            "image_sha256": image_sha256,
            "created_at": created_at,
        }

    def list_group(self, group_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM gallery WHERE group_id = ? ORDER BY id ASC LIMIT ?",
                (group_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def count_group(self, group_id: str) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS total FROM gallery WHERE group_id = ?", (group_id,)
            ).fetchone()
        return int(row["total"])

    def get_person(self, group_id: str, person_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM gallery WHERE group_id = ? AND person_id = ?",
                (group_id, person_id),
            ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------ idempotency
    def get_idempotency(self, key: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT key, fingerprint, status, data_json, created_at "
                "FROM idempotency WHERE key = ?",
                (key,),
            ).fetchone()
        return dict(row) if row else None

    def save_idempotency(
        self, *, key: str, fingerprint: str, status: int, data_json: str, created_at: float
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO idempotency "
                "(key, fingerprint, status, data_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (key, fingerprint, status, data_json, created_at),
            )
            conn.commit()

    def delete_expired_idempotency(self, before: float) -> int:
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM idempotency WHERE created_at < ?", (before,))
            conn.commit()
            return cursor.rowcount
