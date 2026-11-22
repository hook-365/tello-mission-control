"""JSON-file storage for flight sequences, plus a few read-only built-ins.

Each user sequence lives in ``<sequences_dir>/<id>.json``. In Docker that
directory is a mounted volume, so saved routines survive rebuilds.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from app.models.sequences import Sequence, SequenceIn

logger = logging.getLogger(__name__)

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")


class SequenceNotFoundError(Exception):
    pass


class BuiltinSequenceError(Exception):
    """Raised when trying to modify or delete a built-in sequence."""


_BUILTIN_DEFS: list[dict] = [
    {
        "id": "builtin-victory-lap",
        "name": "Victory lap",
        "description": "Climb, fly out 1.5 m, turn around, fly back and finish with a flip. Needs ~2 m of clear space and 50%+ battery.",
        "steps": [
            {"type": "move", "direction": "up", "distance_cm": 50},
            {"type": "move", "direction": "forward", "distance_cm": 150},
            {"type": "rotate", "direction": "cw", "angle_deg": 180},
            {"type": "move", "direction": "forward", "distance_cm": 150},
            {"type": "rotate", "direction": "cw", "angle_deg": 180},
            {"type": "wait", "seconds": 1},
            {"type": "flip", "direction": "back"},
        ],
    },
    {
        "id": "builtin-square-dance",
        "name": "Square dance",
        "description": "A 1 m square with a pause at each corner. Needs ~1.5 m of clear space.",
        "steps": [
            {"type": "move", "direction": "forward", "distance_cm": 100},
            {"type": "rotate", "direction": "cw", "angle_deg": 90},
            {"type": "wait", "seconds": 1},
            {"type": "move", "direction": "forward", "distance_cm": 100},
            {"type": "rotate", "direction": "cw", "angle_deg": 90},
            {"type": "wait", "seconds": 1},
            {"type": "move", "direction": "forward", "distance_cm": 100},
            {"type": "rotate", "direction": "cw", "angle_deg": 90},
            {"type": "wait", "seconds": 1},
            {"type": "move", "direction": "forward", "distance_cm": 100},
            {"type": "rotate", "direction": "cw", "angle_deg": 90},
        ],
    },
    {
        "id": "builtin-elevator-spin",
        "name": "Elevator spin",
        "description": "Rise up, full spin, drop down, spin back. Stays in place, good for small rooms (needs ~1.5 m of headroom above takeoff).",
        "steps": [
            {"type": "move", "direction": "up", "distance_cm": 80},
            {"type": "rotate", "direction": "cw", "angle_deg": 360},
            {"type": "wait", "seconds": 1},
            {"type": "move", "direction": "down", "distance_cm": 60},
            {"type": "rotate", "direction": "ccw", "angle_deg": 360},
        ],
    },
]

BUILTIN_SEQUENCES: dict[str, Sequence] = {
    d["id"]: Sequence(**d, builtin=True) for d in _BUILTIN_DEFS
}


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:40] or "sequence"


class SequenceStore:
    def __init__(self, directory: str | os.PathLike) -> None:
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def directory(self) -> Path:
        return self._dir

    # -- helpers --

    def _path(self, seq_id: str) -> Path:
        if not _ID_RE.match(seq_id):
            raise SequenceNotFoundError(seq_id)
        return self._dir / f"{seq_id}.json"

    def _write(self, seq: Sequence) -> None:
        path = self._path(seq.id)
        fd, tmp = tempfile.mkstemp(dir=self._dir, prefix=".tmp-", suffix=".json")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(seq.model_dump_json(indent=2))
            os.replace(tmp, path)  # atomic on the same filesystem
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def _read(self, path: Path) -> Sequence | None:
        try:
            data = json.loads(path.read_text())
            data["id"] = path.stem
            data["builtin"] = False
            return Sequence(**data)
        except (OSError, ValueError, ValidationError) as e:
            logger.warning("Skipping unreadable sequence file %s: %s", path.name, e)
            return None

    # -- public API --

    def list(self) -> list[Sequence]:
        user = [s for p in sorted(self._dir.glob("*.json")) if (s := self._read(p))]
        user.sort(key=lambda s: s.name.lower())
        return list(BUILTIN_SEQUENCES.values()) + user

    def get(self, seq_id: str) -> Sequence:
        if seq_id in BUILTIN_SEQUENCES:
            return BUILTIN_SEQUENCES[seq_id]
        path = self._path(seq_id)
        if not path.exists():
            raise SequenceNotFoundError(seq_id)
        seq = self._read(path)
        if seq is None:
            raise SequenceNotFoundError(seq_id)
        return seq

    def create(self, data: SequenceIn) -> Sequence:
        now = datetime.now(timezone.utc)
        seq_id = f"{_slugify(data.name)}-{uuid.uuid4().hex[:6]}"
        seq = Sequence(**data.model_dump(), id=seq_id, created_at=now, updated_at=now)
        self._write(seq)
        return seq

    def update(self, seq_id: str, data: SequenceIn) -> Sequence:
        if seq_id in BUILTIN_SEQUENCES:
            raise BuiltinSequenceError(seq_id)
        existing = self.get(seq_id)
        seq = Sequence(
            **data.model_dump(),
            id=seq_id,
            created_at=existing.created_at,
            updated_at=datetime.now(timezone.utc),
        )
        self._write(seq)
        return seq

    def delete(self, seq_id: str) -> None:
        if seq_id in BUILTIN_SEQUENCES:
            raise BuiltinSequenceError(seq_id)
        path = self._path(seq_id)
        if not path.exists():
            raise SequenceNotFoundError(seq_id)
        path.unlink()
