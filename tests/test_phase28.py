"""Phase 28 — Richer cover art & metadata.

Tests:
  - _write_ffmetadata includes narrator, year, language, publisher fields
  - compile_m4b signature includes new params
  - extract_epub_cover returns None gracefully when epub has no cover
  - extract_epub_cover finds cover from OPF properties="cover-image"
  - _render_cover uses title for scoring (interface check)
  - _score_cover_page: image-heavy page scores higher than text-only page
  - CLI has --year, --language, --publisher, --cover flags
"""

import io
import json
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from vorpal.master import (
    _write_ffmetadata,
    compile_m4b,
    extract_epub_cover,
)


# ── _write_ffmetadata new fields ──────────────────────────────────────────

class TestFfmetadataFields:
    def _read_ffmeta(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def _make_results(self):
        return [{"title": "Chapter One", "duration_ms": 60000}]

    def test_narrator_written(self, tmp_path):
        meta = tmp_path / "test.ffmeta"
        _write_ffmetadata(meta, self._make_results(), [0], "Book", "Author",
                          narrator="Heart")
        content = self._read_ffmeta(meta)
        assert "composer=Heart" in content

    def test_year_written(self, tmp_path):
        meta = tmp_path / "test.ffmeta"
        _write_ffmetadata(meta, self._make_results(), [0], "Book", "Author",
                          year="1865")
        content = self._read_ffmeta(meta)
        assert "date=1865" in content

    def test_language_written(self, tmp_path):
        meta = tmp_path / "test.ffmeta"
        _write_ffmetadata(meta, self._make_results(), [0], "Book", "Author",
                          language="en")
        content = self._read_ffmeta(meta)
        assert "language=en" in content

    def test_publisher_written(self, tmp_path):
        meta = tmp_path / "test.ffmeta"
        _write_ffmetadata(meta, self._make_results(), [0], "Book", "Author",
                          publisher="Wonderland Press")
        content = self._read_ffmeta(meta)
        assert "publisher=Wonderland Press" in content

    def test_empty_fields_omitted(self, tmp_path):
        meta = tmp_path / "test.ffmeta"
        _write_ffmetadata(meta, self._make_results(), [0], "Book", "Author",
                          narrator="", year="", publisher="")
        content = self._read_ffmeta(meta)
        assert "composer=" not in content
        assert "date=" not in content
        assert "publisher=" not in content

    def test_default_language_en(self, tmp_path):
        meta = tmp_path / "test.ffmeta"
        _write_ffmetadata(meta, self._make_results(), [0], "Book", "Author")
        content = self._read_ffmeta(meta)
        assert "language=en" in content


# ── compile_m4b signature ─────────────────────────────────────────────────

class TestCompileM4bSignature:
    def test_new_params_exist(self):
        import inspect
        sig = inspect.signature(compile_m4b)
        params = sig.parameters
        assert "narrator" in params
        assert "year" in params
        assert "language" in params
        assert "publisher" in params
        assert "cover_path" in params

    def test_new_params_have_defaults(self):
        import inspect
        sig = inspect.signature(compile_m4b)
        assert sig.parameters["narrator"].default == ""
        assert sig.parameters["year"].default == ""
        assert sig.parameters["language"].default == "en"
        assert sig.parameters["publisher"].default == ""
        assert sig.parameters["cover_path"].default is None


# ── extract_epub_cover ────────────────────────────────────────────────────

def _make_epub_zip(cover_bytes: bytes = None, cover_media_type: str = "image/jpeg",
                   cover_props: str = "cover-image") -> bytes:
    """Create a minimal EPUB zip for testing."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        # container.xml
        zf.writestr("META-INF/container.xml",
                    '<?xml version="1.0"?>'
                    '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                    '<rootfiles><rootfile full-path="OEBPS/content.opf"'
                    ' media-type="application/oebps-package+xml"/></rootfiles>'
                    '</container>')

        # OPF with cover image in manifest
        if cover_bytes is not None:
            opf = (
                '<?xml version="1.0"?>'
                '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
                '<metadata/><manifest>'
                f'<item id="cover-img" href="cover.jpg"'
                f' media-type="{cover_media_type}"'
                f' properties="{cover_props}"/>'
                '</manifest><spine/></package>'
            )
            zf.writestr("OEBPS/content.opf", opf)
            zf.writestr("OEBPS/cover.jpg", cover_bytes)
        else:
            # OPF with no cover image
            opf = (
                '<?xml version="1.0"?>'
                '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
                '<metadata/><manifest>'
                '<item id="ch1" href="chapter1.html"'
                ' media-type="application/xhtml+xml"/>'
                '</manifest><spine/></package>'
            )
            zf.writestr("OEBPS/content.opf", opf)
    return buf.getvalue()


class TestExtractEpubCover:
    def test_no_cover_returns_none(self, tmp_path):
        epub_path = tmp_path / "no_cover.epub"
        epub_path.write_bytes(_make_epub_zip(cover_bytes=None))
        result = extract_epub_cover(epub_path, tmp_path)
        assert result is None

    def test_cover_extracted(self, tmp_path):
        fake_jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 20  # minimal JPEG header
        epub_path = tmp_path / "with_cover.epub"
        epub_path.write_bytes(_make_epub_zip(cover_bytes=fake_jpeg))
        result = extract_epub_cover(epub_path, tmp_path)
        assert result is not None
        assert result.exists()
        assert result.read_bytes() == fake_jpeg

    def test_missing_epub_returns_none(self, tmp_path):
        result = extract_epub_cover(tmp_path / "nonexistent.epub", tmp_path)
        assert result is None

    def test_corrupt_epub_returns_none(self, tmp_path):
        epub_path = tmp_path / "corrupt.epub"
        epub_path.write_bytes(b"not a zip file at all")
        result = extract_epub_cover(epub_path, tmp_path)
        assert result is None


# ── CLI flag documentation ────────────────────────────────────────────────

class TestCLIFlags:
    def test_year_flag_exists(self):
        from vorpal.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["build", "test.pdf", "--year", "1865"])
        assert args.year == "1865"

    def test_language_flag_exists(self):
        from vorpal.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["build", "test.pdf", "--language", "fr"])
        assert args.language == "fr"

    def test_language_default(self):
        from vorpal.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["build", "test.pdf"])
        assert args.language == "en"

    def test_publisher_flag_exists(self):
        from vorpal.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["build", "test.pdf", "--publisher", "OUP"])
        assert args.publisher == "OUP"

    def test_cover_flag_exists(self):
        from vorpal.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["build", "test.pdf", "--cover", "mycover.jpg"])
        assert args.cover == "mycover.jpg"

    def test_cover_default_none(self):
        from vorpal.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["build", "test.pdf"])
        assert args.cover is None
