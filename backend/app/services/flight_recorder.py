from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models.telemetry import TelemetryFrame

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    ended_at TEXT
);
CREATE TABLE IF NOT EXISTS telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    ts TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    ts TEXT NOT NULL,
    command TEXT NOT NULL,
    params TEXT NOT NULL,
    result TEXT NOT NULL,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_telemetry_session ON telemetry(session_id, id);
CREATE INDEX IF NOT EXISTS idx_commands_session ON commands(session_id, id);
"""

_SESSION_SUMMARY = """
SELECT s.id, s.started_at, s.ended_at,
       (SELECT COUNT(*) FROM telemetry t WHERE t.session_id = s.id) AS telemetry_frames,
       (SELECT COUNT(*) FROM commands c WHERE c.session_id = s.id) AS commands
FROM sessions s
"""


_SEQUENCE_COMMANDS = {
    "running": "sequence_start",
    "completed": "sequence_completed",
    "aborted": "sequence_aborted",
    "failed": "sequence_failed",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FlightRecorder:
    """Persists every telemetry frame and command to SQLite, grouped into sessions.

    A session spans one drone connection: it opens on ``connect`` (or on the first
    frame seen, if the recorder attached late) and closes on ``disconnect``.

    ``on_telemetry`` / ``on_command`` are registered as broadcast subscribers.
    Those broadcasters drop any subscriber that raises, so both methods swallow
    their errors: a failed write must not end recording for the rest of the flight.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._db: sqlite3.Connection | None = None
        self._db_lock = threading.Lock()
        self._session_id: int | None = None
        self._last_sequence_key: tuple | None = None

    @property
    def active_session_id(self) -> int | None:
        return self._session_id

    # -- Lifecycle --

    async def start(self) -> None:
        await asyncio.to_thread(self._open)
        logger.info("FlightRecorder writing to %s", self._path)

    async def stop(self) -> None:
        await asyncio.to_thread(self._close)

    def _open(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self._path, check_same_thread=False)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.executescript(_SCHEMA)
        # Sessions left open by a crash: end them at their last recorded frame.
        db.execute(
            """
            UPDATE sessions SET ended_at = COALESCE(
                (SELECT MAX(ts) FROM telemetry WHERE session_id = sessions.id), started_at)
            WHERE ended_at IS NULL
            """
        )
        db.commit()
        self._db = db

    def _close(self) -> None:
        with self._db_lock:
            if self._db is None:
                return
            self._end_session_locked()
            self._db.close()
            self._db = None

    # -- Broadcast subscribers (must never raise) --

    async def on_telemetry(self, frame: TelemetryFrame) -> None:
        try:
            await asyncio.to_thread(
                self._write_telemetry,
                frame.timestamp.isoformat(),
                frame.data.model_dump_json(),
            )
        except Exception as e:
            logger.warning("Flight log: telemetry write failed: %s", e)

    async def on_command(self, entry: dict) -> None:
        # The same fan-out carries sequence progress and media events. Commands
        # are stored as they are; a sequence run is stored as its start and its
        # outcome (each step already arrives as its own command); the rest is
        # live-UI chatter and is skipped.
        kind = entry.get("type")
        if kind == "command_log":
            data = entry.get("data", {})
        elif kind == "sequence_progress":
            data = self._sequence_transition(entry.get("data", {}), entry.get("timestamp"))
            if data is None:
                return
        else:
            return
        try:
            await asyncio.to_thread(self._write_command, data)
        except Exception as e:
            logger.warning("Flight log: command write failed: %s", e)

    def _sequence_transition(self, status: dict, ts: str | None) -> dict | None:
        """Turn a run's progress stream into two log rows: started, and how it ended."""
        state = status.get("status")
        key = (status.get("run_id"), state)
        if state not in _SEQUENCE_COMMANDS or key == self._last_sequence_key:
            return None
        self._last_sequence_key = key
        bad = state in ("aborted", "failed")
        return {
            "command": _SEQUENCE_COMMANDS[state],
            "params": {"name": status.get("sequence_name") or "unsaved sequence"},
            "result": "error" if bad else "ok",
            "error": (status.get("message") or state) if bad else None,
            "timestamp": ts or _now(),
        }

    # -- Writes (worker thread) --

    def _ensure_session_locked(self, ts: str) -> int:
        if self._session_id is None:
            cur = self._db.execute("INSERT INTO sessions (started_at) VALUES (?)", (ts,))
            self._session_id = cur.lastrowid
        return self._session_id

    def _end_session_locked(self) -> None:
        if self._session_id is None:
            return
        self._db.execute(
            "UPDATE sessions SET ended_at = ? WHERE id = ?", (_now(), self._session_id)
        )
        self._db.commit()
        self._session_id = None

    def _write_telemetry(self, ts: str, data_json: str) -> None:
        with self._db_lock:
            if self._db is None:
                return
            session_id = self._ensure_session_locked(ts)
            self._db.execute(
                "INSERT INTO telemetry (session_id, ts, data) VALUES (?, ?, ?)",
                (session_id, ts, data_json),
            )
            self._db.commit()

    def _write_command(self, data: dict) -> None:
        command = data.get("command", "")
        ts = data.get("timestamp") or _now()
        with self._db_lock:
            if self._db is None:
                return
            if command == "disconnect" and self._session_id is None:
                return
            session_id = self._ensure_session_locked(ts)
            self._db.execute(
                "INSERT INTO commands (session_id, ts, command, params, result, error)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    ts,
                    command,
                    json.dumps(data.get("params") or {}),
                    data.get("result", ""),
                    data.get("error"),
                ),
            )
            self._db.commit()
            if command == "disconnect":
                self._end_session_locked()

    # -- Reads --

    async def list_sessions(self) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._list_sessions)

    async def get_session(self, session_id: int) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_session, session_id)

    async def delete_session(self, session_id: int) -> bool:
        """Delete a session and its rows. Returns False if it does not exist."""
        return await asyncio.to_thread(self._delete_session, session_id)

    def _summary(self, row: sqlite3.Row) -> dict[str, Any]:
        return {**dict(row), "active": row["id"] == self._session_id}

    def _list_sessions(self) -> list[dict[str, Any]]:
        with self._db_lock:
            rows = self._db.execute(_SESSION_SUMMARY + " ORDER BY s.id DESC").fetchall()
            return [self._summary(r) for r in rows]

    def _get_session(self, session_id: int) -> dict[str, Any] | None:
        with self._db_lock:
            row = self._db.execute(_SESSION_SUMMARY + " WHERE s.id = ?", (session_id,)).fetchone()
            if row is None:
                return None
            telemetry = self._db.execute(
                "SELECT ts, data FROM telemetry WHERE session_id = ? ORDER BY id", (session_id,)
            ).fetchall()
            commands = self._db.execute(
                "SELECT ts, command, params, result, error FROM commands"
                " WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
            return {
                **self._summary(row),
                "telemetry": [
                    {"timestamp": t["ts"], "data": json.loads(t["data"])} for t in telemetry
                ],
                "command_log": [
                    {
                        "timestamp": c["ts"],
                        "command": c["command"],
                        "params": json.loads(c["params"]),
                        "result": c["result"],
                        "error": c["error"],
                    }
                    for c in commands
                ],
            }

    def _delete_session(self, session_id: int) -> bool:
        with self._db_lock:
            cur = self._db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            self._db.commit()
            return cur.rowcount > 0
