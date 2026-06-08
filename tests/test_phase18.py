"""Phase 18 — Library / batch mode tests.

All tests use synthetic TXT fixtures; no TTS/GPU calls are made.
The library discovery, per-book isolation, report generation, and
resume behaviour are exercised independently of real book data.
"""

import argparse
from pathlib import Path

import pytest

from vorpal.cli import (
    _discover_books,
    _write_library_report,
    _build_one_library_book,
    build_parser,
)


# ── helpers ───────────────────────────────────────────────────────────────────


def _simple_txt(path: Path, n_chapters: int = 2) -> None:
    """Write a minimal multi-chapter TXT book."""
    body = "\n\n".join(
        f"# Chapter {i}\n\nText for chapter {i}." for i in range(1, n_chapters + 1)
    )
    path.write_text(body, encoding="utf-8")


def _lib_args(**kw) -> argparse.Namespace:
    defaults = dict(voice="af_heart", speed=1.0, dpi=300, stop_after="segment", draft=False)
    defaults.update(kw)
    return argparse.Namespace(directory=".", **defaults)


# ── _discover_books ────────────────────────────────────────────────────────────


def test_discover_finds_pdf_epub_txt(tmp_path):
    (tmp_path / "novel.pdf").write_bytes(b"%PDF-1.4 fake")
    (tmp_path / "story.epub").write_bytes(b"PK fake")
    (tmp_path / "essay.txt").write_text("# Ch\n\nHello.\n")
    (tmp_path / "notes.md").write_text("not a book")
    names = {b.name for b in _discover_books(tmp_path)}
    assert "novel.pdf" in names
    assert "story.epub" in names
    assert "essay.txt" in names
    assert "notes.md" not in names


def test_discover_empty_dir(tmp_path):
    assert _discover_books(tmp_path) == []


def test_discover_sorted_within_extension(tmp_path):
    for name in ("zebra.txt", "alpha.txt", "mango.txt"):
        (tmp_path / name).write_text("# Ch\n\nHi.\n")
    txts = [b.name for b in _discover_books(tmp_path) if b.suffix == ".txt"]
    assert txts == sorted(txts)


def test_discover_non_recursive(tmp_path):
    """Files inside subdirectories (including workdirs) are not returned."""
    (tmp_path / "novel.txt").write_text("# Ch\n\nHi.\n")
    sub = tmp_path / "novel_workdir"
    sub.mkdir()
    (sub / "inside.txt").write_text("# Ch\n\nInside.\n")
    names = [b.name for b in _discover_books(tmp_path)]
    assert "novel.txt" in names
    assert "inside.txt" not in names


# ── _write_library_report ──────────────────────────────────────────────────────


def test_report_created_in_lib_dir(tmp_path):
    _write_library_report(tmp_path, [])
    assert (tmp_path / "library_report.md").exists()


def test_report_contains_file_names(tmp_path):
    results = [
        {"file": "alpha.txt", "status": "success",      "detail": ""},
        {"file": "beta.txt",  "status": "needs_review", "detail": "review gate"},
        {"file": "gamma.txt", "status": "failed",       "detail": "parse error"},
    ]
    content = _write_library_report(tmp_path, results).read_text()
    for r in results:
        assert r["file"] in content
        assert r["status"] in content


def test_report_summary_counts(tmp_path):
    results = [
        {"file": "a.txt", "status": "success"},
        {"file": "b.txt", "status": "success"},
        {"file": "c.txt", "status": "failed"},
        {"file": "d.txt", "status": "needs_review"},
    ]
    content = _write_library_report(tmp_path, results).read_text()
    assert "2 success" in content
    assert "1 failed" in content
    assert "1 needs review" in content


def test_report_empty_list(tmp_path):
    content = _write_library_report(tmp_path, []).read_text()
    assert "0 success" in content or "Books processed: 0" in content


# ── _build_one_library_book ────────────────────────────────────────────────────


def test_success_on_clean_build(tmp_path, monkeypatch):
    book = tmp_path / "ok.txt"
    _simple_txt(book)
    monkeypatch.setattr("vorpal.cli.cmd_build", lambda _: None)
    status, _ = _build_one_library_book(_lib_args(), book)
    assert status == "success"


def test_exception_becomes_failed(tmp_path, monkeypatch):
    book = tmp_path / "bad.txt"
    _simple_txt(book)
    monkeypatch.setattr("vorpal.cli.cmd_build", lambda _: (_ for _ in ()).throw(RuntimeError("boom")))
    status, detail = _build_one_library_book(_lib_args(), book)
    assert status == "failed"
    assert "boom" in detail


def test_system_exit_zero_is_success(tmp_path, monkeypatch):
    book = tmp_path / "stopped.txt"
    _simple_txt(book)

    def _exit_zero(_):
        raise SystemExit(0)

    monkeypatch.setattr("vorpal.cli.cmd_build", _exit_zero)
    status, _ = _build_one_library_book(_lib_args(stop_after="extract"), book)
    assert status == "success"


def test_system_exit_review_message_is_needs_review(tmp_path, monkeypatch):
    book = tmp_path / "pending.txt"
    _simple_txt(book)

    def _exit_review(_):
        raise SystemExit("vorpal review pending.txt --approve")

    monkeypatch.setattr("vorpal.cli.cmd_build", _exit_review)
    status, _ = _build_one_library_book(_lib_args(stop_after=None), book)
    assert status == "needs_review"


def test_system_exit_non_review_is_failed(tmp_path, monkeypatch):
    book = tmp_path / "broken.txt"
    _simple_txt(book)

    def _exit_err(_):
        raise SystemExit("ERROR: ffmpeg not found")

    monkeypatch.setattr("vorpal.cli.cmd_build", _exit_err)
    status, detail = _build_one_library_book(_lib_args(), book)
    assert status == "failed"
    assert "ffmpeg" in detail


def test_workdir_placed_next_to_book(tmp_path, monkeypatch):
    """Library builds use the book's directory as output root, not CWD."""
    book = tmp_path / "mybook.txt"
    _simple_txt(book)
    captured = {}

    def _capture(book_args):
        captured["output"] = book_args.output

    monkeypatch.setattr("vorpal.cli.cmd_build", _capture)
    _build_one_library_book(_lib_args(), book)
    # output should be inside tmp_path (not a relative path)
    assert captured["output"].startswith(str(tmp_path))
    assert captured["output"].endswith("mybook")


def test_failure_does_not_abort_other_books(tmp_path, monkeypatch):
    """One book failing should not prevent other books from being attempted."""
    for name in ("ok1.txt", "bad.txt", "ok2.txt"):
        _simple_txt(tmp_path / name)

    call_log = []

    def _maybe_fail(book_args):
        call_log.append(Path(book_args.input).name)
        if "bad" in book_args.input:
            raise ValueError("simulated failure")

    monkeypatch.setattr("vorpal.cli.cmd_build", _maybe_fail)

    results = []
    for book_path in _discover_books(tmp_path):
        status, detail = _build_one_library_book(_lib_args(), book_path)
        results.append({"file": book_path.name, "status": status})

    # All three were attempted
    assert len(call_log) == 3
    statuses = {r["file"]: r["status"] for r in results}
    assert statuses["ok1.txt"] == "success"
    assert statuses["bad.txt"] == "failed"
    assert statuses["ok2.txt"] == "success"


# ── parser ────────────────────────────────────────────────────────────────────


def test_parser_has_library_subcommand():
    p = build_parser()
    args = p.parse_args(["library", "/some/dir"])
    assert args.command == "library"
    assert args.directory == "/some/dir"


def test_parser_library_defaults():
    p = build_parser()
    args = p.parse_args(["library", "/dir"])
    assert args.voice == "af_heart"
    assert args.speed == 1.0
    assert args.stop_after is None
    assert args.draft is False


def test_parser_library_stop_after():
    p = build_parser()
    args = p.parse_args(["library", "/dir", "--stop-after", "segment"])
    assert args.stop_after == "segment"


def test_parser_library_voice_and_draft():
    p = build_parser()
    args = p.parse_args(["library", "/dir", "--voice", "bm_george", "--draft"])
    assert args.voice == "bm_george"
    assert args.draft is True


# ── end-to-end with real TXT parsing ─────────────────────────────────────────


def test_e2e_three_txt_books_stop_after_segment(tmp_path):
    """Library mode builds 3 TXT books to segment stage without TTS/GPU."""
    for name in ("book_a.txt", "book_b.txt", "book_c.txt"):
        _simple_txt(tmp_path / name, n_chapters=2)

    results = []
    for book_path in _discover_books(tmp_path):
        status, detail = _build_one_library_book(_lib_args(stop_after="segment"), book_path)
        results.append({"file": book_path.name, "status": status, "detail": detail})

    assert len(results) == 3
    failures = [r for r in results if r["status"] != "success"]
    assert failures == [], failures

    # Each book should have a workdir with chapter_texts inside the library dir
    for name in ("book_a", "book_b", "book_c"):
        wd = tmp_path / f"{name}_workdir"
        assert wd.is_dir(), f"workdir missing: {wd}"
        ct = wd / "chapter_texts"
        assert ct.is_dir(), f"chapter_texts missing in {wd}"

    # Report should be written
    report = _write_library_report(tmp_path, results)
    content = report.read_text()
    assert "3 success" in content
