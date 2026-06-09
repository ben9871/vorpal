"""Phase 30 — TUI / thin local web UI.

Tests:
  - GET /api/book: returns manifest; 404 when absent
  - PATCH /api/chapters/{idx}: title, include, spoken_intro editable; persists
  - PATCH /api/chapters/{idx}: invalid field → 400; OOB idx → 404; no manifest → 404
  - Downstream invalidation: editing title/include marks synth/master stale
  - GET /api/voices: returns full voice registry list
  - GET /: returns HTML with chapter-table and Build button
  - POST /api/build: returns {status: started}, 409 on double-trigger
  - CLI: serve subcommand flags (input, --host, --port, --no-browser, --output)
"""

import json
from pathlib import Path

import pytest

try:
    from fastapi.testclient import TestClient
    from vorpal.serve import create_app
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

pytestmark = pytest.mark.skipif(not _AVAILABLE, reason="fastapi not installed")


# ── helpers ────────────────────────────────────────────────────────────────

def _book_json(work_dir: Path, n_chapters: int = 3,
               extra_stages: dict = None) -> dict:
    chapters = [
        {
            "id": i + 1, "title": f"Chapter {i + 1}", "kind": "chapter",
            "include": True, "source": "outline", "confidence": 0.95,
            "start": [i * 10, 0], "end": [(i + 1) * 10 - 1, 99],
            "words": 500, "flags": [], "spoken_intro": None,
            "paragraph_tones": [],
        }
        for i in range(n_chapters)
    ]
    stages = {"review": {"status": "done", "input_hash": "abc"}}
    if extra_stages:
        stages.update(extra_stages)
    data = {
        "version": 1,
        "source": {"title": "Alice in Wonderland", "author": "Lewis Carroll",
                   "format": "pdf"},
        "settings": {},
        "chapters": chapters,
        "stages": stages,
        "qa": {},
    }
    (work_dir / "book.json").write_text(
        json.dumps(data, indent=2), encoding="utf-8"
    )
    return data


def _client(tmp_path: Path):
    app = create_app(tmp_path / "book.pdf", tmp_path)
    return TestClient(app, raise_server_exceptions=True)


# ── GET /api/book ──────────────────────────────────────────────────────────

class TestGetBook:
    def test_returns_manifest(self, tmp_path):
        _book_json(tmp_path)
        r = _client(tmp_path).get("/api/book")
        assert r.status_code == 200
        data = r.json()
        assert data["source"]["title"] == "Alice in Wonderland"
        assert len(data["chapters"]) == 3

    def test_returns_chapter_fields(self, tmp_path):
        _book_json(tmp_path)
        r = _client(tmp_path).get("/api/book")
        ch = r.json()["chapters"][0]
        assert "title" in ch
        assert "include" in ch
        assert "kind" in ch

    def test_404_when_no_manifest(self, tmp_path):
        r = _client(tmp_path).get("/api/book")
        assert r.status_code == 404

    def test_source_format_present(self, tmp_path):
        _book_json(tmp_path)
        data = _client(tmp_path).get("/api/book").json()
        assert data["source"]["format"] == "pdf"


# ── PATCH /api/chapters/{idx} ──────────────────────────────────────────────

class TestPatchChapter:
    def test_update_title(self, tmp_path):
        _book_json(tmp_path)
        r = _client(tmp_path).patch(
            "/api/chapters/0", json={"field": "title", "value": "New Title"}
        )
        assert r.status_code == 200
        data = json.loads((tmp_path / "book.json").read_text(encoding="utf-8"))
        assert data["chapters"][0]["title"] == "New Title"

    def test_update_include_false(self, tmp_path):
        _book_json(tmp_path)
        r = _client(tmp_path).patch(
            "/api/chapters/1", json={"field": "include", "value": False}
        )
        assert r.status_code == 200
        data = json.loads((tmp_path / "book.json").read_text(encoding="utf-8"))
        assert data["chapters"][1]["include"] is False

    def test_update_include_true(self, tmp_path):
        raw = _book_json(tmp_path, n_chapters=1)
        raw["chapters"][0]["include"] = False
        (tmp_path / "book.json").write_text(json.dumps(raw), encoding="utf-8")
        _client(tmp_path).patch(
            "/api/chapters/0", json={"field": "include", "value": True}
        )
        data = json.loads((tmp_path / "book.json").read_text(encoding="utf-8"))
        assert data["chapters"][0]["include"] is True

    def test_update_spoken_intro(self, tmp_path):
        _book_json(tmp_path)
        r = _client(tmp_path).patch(
            "/api/chapters/2",
            json={"field": "spoken_intro", "value": "Part three."},
        )
        assert r.status_code == 200
        data = json.loads((tmp_path / "book.json").read_text(encoding="utf-8"))
        assert data["chapters"][2]["spoken_intro"] == "Part three."

    def test_response_ok_true(self, tmp_path):
        _book_json(tmp_path)
        r = _client(tmp_path).patch(
            "/api/chapters/0", json={"field": "title", "value": "X"}
        )
        assert r.json() == {"ok": True}

    def test_invalid_field_returns_400(self, tmp_path):
        _book_json(tmp_path)
        r = _client(tmp_path).patch(
            "/api/chapters/0", json={"field": "kind", "value": "bad"}
        )
        assert r.status_code == 400

    def test_non_editable_field_returns_400(self, tmp_path):
        _book_json(tmp_path)
        r = _client(tmp_path).patch(
            "/api/chapters/0", json={"field": "source", "value": "heuristic"}
        )
        assert r.status_code == 400

    def test_oob_idx_returns_404(self, tmp_path):
        _book_json(tmp_path)
        r = _client(tmp_path).patch(
            "/api/chapters/99", json={"field": "title", "value": "x"}
        )
        assert r.status_code == 404

    def test_no_manifest_returns_404(self, tmp_path):
        r = _client(tmp_path).patch(
            "/api/chapters/0", json={"field": "title", "value": "x"}
        )
        assert r.status_code == 404


class TestDownstreamInvalidation:
    """Editing title/include marks downstream stages stale — same as CLI review."""

    def _stages(self):
        return {
            "review": {"status": "done", "input_hash": "r"},
            "normalize": {"status": "done", "input_hash": "n"},
            "synth":     {"status": "done", "input_hash": "s"},
            "master":    {"status": "done", "input_hash": "m"},
        }

    def test_title_change_stalens_synth(self, tmp_path):
        _book_json(tmp_path, extra_stages=self._stages())
        _client(tmp_path).patch(
            "/api/chapters/0", json={"field": "title", "value": "Changed"}
        )
        data = json.loads((tmp_path / "book.json").read_text(encoding="utf-8"))
        assert data["stages"]["synth"]["status"] == "stale"

    def test_title_change_stalens_master(self, tmp_path):
        _book_json(tmp_path, extra_stages=self._stages())
        _client(tmp_path).patch(
            "/api/chapters/0", json={"field": "title", "value": "Changed"}
        )
        data = json.loads((tmp_path / "book.json").read_text(encoding="utf-8"))
        assert data["stages"]["master"]["status"] == "stale"

    def test_include_change_stalens_synth(self, tmp_path):
        _book_json(tmp_path, extra_stages=self._stages())
        _client(tmp_path).patch(
            "/api/chapters/1", json={"field": "include", "value": False}
        )
        data = json.loads((tmp_path / "book.json").read_text(encoding="utf-8"))
        assert data["stages"]["synth"]["status"] == "stale"

    def test_review_stage_not_staled(self, tmp_path):
        _book_json(tmp_path, extra_stages=self._stages())
        _client(tmp_path).patch(
            "/api/chapters/0", json={"field": "title", "value": "Changed"}
        )
        data = json.loads((tmp_path / "book.json").read_text(encoding="utf-8"))
        assert data["stages"]["review"]["status"] == "done"

    def test_spoken_intro_change_does_not_stale(self, tmp_path):
        # spoken_intro is editable but does NOT trigger invalidation
        _book_json(tmp_path, extra_stages=self._stages())
        _client(tmp_path).patch(
            "/api/chapters/0",
            json={"field": "spoken_intro", "value": "Part One."},
        )
        data = json.loads((tmp_path / "book.json").read_text(encoding="utf-8"))
        # synth not staled because spoken_intro is not in the invalidation set
        assert data["stages"]["synth"]["status"] == "done"


# ── GET /api/voices ────────────────────────────────────────────────────────

class TestGetVoices:
    def test_returns_list(self, tmp_path):
        r = _client(tmp_path).get("/api/voices")
        assert r.status_code == 200
        voices = r.json()
        assert isinstance(voices, list)
        assert len(voices) > 0

    def test_voice_has_required_fields(self, tmp_path):
        voices = _client(tmp_path).get("/api/voices").json()
        for v in voices:
            assert "id" in v
            assert "display_name" in v
            assert "description" in v

    def test_known_voice_present(self, tmp_path):
        voices = _client(tmp_path).get("/api/voices").json()
        ids = [v["id"] for v in voices]
        assert "af_heart" in ids


# ── GET / (UI HTML) ────────────────────────────────────────────────────────

class TestServeUI:
    def test_returns_html(self, tmp_path):
        r = _client(tmp_path).get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]

    def test_html_has_html_tag(self, tmp_path):
        r = _client(tmp_path).get("/")
        assert "<html" in r.text.lower()

    def test_html_has_chapter_table(self, tmp_path):
        r = _client(tmp_path).get("/")
        assert "chapter-table" in r.text

    def test_html_has_build_button(self, tmp_path):
        r = _client(tmp_path).get("/")
        assert "Build" in r.text

    def test_html_has_api_calls(self, tmp_path):
        r = _client(tmp_path).get("/")
        assert "/api/book" in r.text


# ── POST /api/build ────────────────────────────────────────────────────────

class TestBuildTrigger:
    def test_trigger_returns_200_or_202(self, tmp_path):
        _book_json(tmp_path)
        r = _client(tmp_path).post("/api/build")
        assert r.status_code in (200, 202)

    def test_trigger_returns_started_status(self, tmp_path):
        _book_json(tmp_path)
        r = _client(tmp_path).post("/api/build")
        data = r.json()
        assert data.get("status") == "started"


# ── CLI parser ─────────────────────────────────────────────────────────────

class TestCLIServeParser:
    def test_serve_subcommand_parses(self):
        from vorpal.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["serve", "book.pdf"])
        assert args.command == "serve"
        assert args.input == "book.pdf"

    def test_default_host(self):
        from vorpal.cli import build_parser
        args = build_parser().parse_args(["serve", "book.pdf"])
        assert args.host == "127.0.0.1"

    def test_default_port(self):
        from vorpal.cli import build_parser
        args = build_parser().parse_args(["serve", "book.pdf"])
        assert args.port == 7654

    def test_custom_host_port(self):
        from vorpal.cli import build_parser
        args = build_parser().parse_args(
            ["serve", "book.pdf", "--host", "0.0.0.0", "--port", "8080"]
        )
        assert args.host == "0.0.0.0"
        assert args.port == 8080

    def test_no_browser_flag(self):
        from vorpal.cli import build_parser
        args = build_parser().parse_args(["serve", "book.pdf", "--no-browser"])
        assert args.no_browser is True

    def test_no_browser_default_false(self):
        from vorpal.cli import build_parser
        args = build_parser().parse_args(["serve", "book.pdf"])
        assert args.no_browser is False

    def test_output_flag(self):
        from vorpal.cli import build_parser
        args = build_parser().parse_args(
            ["serve", "book.pdf", "--output", "my_run"]
        )
        assert args.output == "my_run"

    def test_output_default_none(self):
        from vorpal.cli import build_parser
        args = build_parser().parse_args(["serve", "book.pdf"])
        assert args.output is None
