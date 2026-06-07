"""The book manifest (book.json) — single source of truth for a build.

Replaces v0's file-existence resume with content-addressed staleness: every
stage records a hash of its inputs (source PDF + relevant settings + upstream
artifact). If the hash changes, the stage — and everything downstream — is
stale and re-runs. Nothing stale is ever silently reused.
"""

import hashlib
import json
from pathlib import Path

MANIFEST_VERSION = 1
MANIFEST_NAME = "book.json"

# Stage order defines what "downstream" means for invalidation.
STAGE_ORDER = ["ingest", "extract", "segment", "review", "normalize", "synth",
               "master", "package"]


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def hash_parts(*parts) -> str:
    """Stable hash of heterogeneous inputs (strings, numbers, dicts)."""
    h = hashlib.sha256()
    for part in parts:
        if isinstance(part, (dict, list)):
            part = json.dumps(part, sort_keys=True, ensure_ascii=False)
        h.update(str(part).encode("utf-8"))
        h.update(b"\x1f")
    return h.hexdigest()


class Manifest:
    def __init__(self, path: Path, data: dict):
        self.path = path
        self.data = data

    # ── lifecycle ─────────────────────────────────────

    @classmethod
    def load_or_create(cls, work_dir: Path) -> "Manifest":
        path = work_dir / MANIFEST_NAME
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("version") != MANIFEST_VERSION:
                # Future migrations land here; for now, start over.
                data = cls._empty()
        else:
            data = cls._empty()
        return cls(path, data)

    @staticmethod
    def _empty() -> dict:
        return {
            "version": MANIFEST_VERSION,
            "source": {},
            "settings": {},
            "pages": [],
            "chapters": [],
            "stages": {},
            "qa": {},
        }

    def save(self) -> None:
        self.path.write_text(
            json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    # ── convenience accessors ─────────────────────────

    @property
    def source(self) -> dict:
        return self.data["source"]

    @property
    def settings(self) -> dict:
        return self.data["settings"]

    @property
    def qa(self) -> dict:
        return self.data["qa"]

    # ── stage staleness ───────────────────────────────

    def stage(self, name: str) -> dict:
        return self.data["stages"].get(name, {})

    def stage_fresh(self, name: str, input_hash: str) -> bool:
        """True if the stage completed with these exact inputs and its
        artifact still exists on disk."""
        st = self.stage(name)
        if st.get("status") != "done" or st.get("input_hash") != input_hash:
            return False
        artifact = st.get("artifact")
        if artifact and not (self.path.parent / artifact).exists():
            return False
        return True

    def stage_done(self, name: str, input_hash: str, artifact: str = None) -> None:
        self.data["stages"][name] = {
            "status": "done",
            "input_hash": input_hash,
            **({"artifact": artifact} if artifact else {}),
        }
        self._invalidate_downstream(name)
        self.save()

    def _invalidate_downstream(self, name: str) -> None:
        """Mark every later stage stale (their inputs just changed)."""
        if name not in STAGE_ORDER:
            return
        for later in STAGE_ORDER[STAGE_ORDER.index(name) + 1:]:
            st = self.data["stages"].get(later)
            if st and st.get("status") == "done":
                st["status"] = "stale"
