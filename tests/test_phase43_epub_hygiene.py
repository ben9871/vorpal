"""Phase 43: EPUB narration hygiene (repeated page headers, endnote markers).

Found during the Trotsky Volume 1 production build: marxists.org EPUB
conversions repeat a page-header line at the top of every spine item, and
inline endnote markers like "[47]" would be narrated as "forty-seven".
"""

from vorpal.extract.epub import (
    detect_repeated_header,
    strip_endnote_markers,
    strip_repeated_headers,
    extract_epub,
)
from vorpal.qa.fidelity import compare_chapters, _apply_pipeline_hygiene

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from test_phase41_fidelity import _make_epub, PARA, PARA2  # noqa: E402


HEADER = "Leon Trotsky: 1918 - How The Revolution Armed/Volume I"


def _body(label, *paras):
    return "\n\n".join([f"{HEADER} ({label})"] + list(paras))


# ── endnote markers ───────────────────────────────────────────────────────

def test_strip_endnote_markers_digits():
    assert strip_endnote_markers("The note continues here.[47] More.") == \
        "The note continues here. More."
    assert strip_endnote_markers("The Spring of 1918[3]") == "The Spring of 1918"
    assert strip_endnote_markers("Up to [123] three digits.") == "Up to  three digits."


def test_strip_endnote_markers_preserves_text_and_years():
    # textual editorial notes and bracketed years are not markers
    s = "[From Pravda, March 21, 1918.] The year [1918] mattered."
    assert strip_endnote_markers(s) == s


# ── repeated header detection ─────────────────────────────────────────────

def test_detect_repeated_header():
    bodies = [_body("We Need an Army", PARA),
              _body("Our Task", PARA2),
              _body("Two Roads", PARA),
              _body("The New Army", PARA2),
              "Cover"]  # odd one out
    pattern = detect_repeated_header(bodies)
    assert pattern is not None
    assert pattern.startswith(HEADER[:15])
    # the varying parenthetical is not part of the pattern
    assert "We Need an Army" not in pattern


def test_no_header_detected_on_short_common_prefix():
    # Chapters legitimately starting with the same word are not headers
    bodies = [f"The chapter {i} begins differently here. {PARA}"
              for i in range(6)]
    assert detect_repeated_header(bodies) is None


def test_no_header_detected_below_min_sections():
    bodies = [_body("A", PARA), _body("B", PARA2), _body("C", PARA)]
    assert detect_repeated_header(bodies) is None


def test_strip_repeated_headers_drops_all_occurrences():
    # v2 split-file pattern: header appears twice in a merged body
    body = "\n\n".join([f"{HEADER} (X)", "Stub title", f"{HEADER} (X)", PARA])
    out, n = strip_repeated_headers(body, HEADER)
    assert n == 2
    assert HEADER not in out
    assert PARA in out and "Stub title" in out


def test_strip_repeated_headers_failsafe_never_empties():
    body = f"{HEADER} (Only)"
    out, n = strip_repeated_headers(body, HEADER)
    assert out == body and n == 0


# ── end-to-end through extract_epub ───────────────────────────────────────

def test_extract_epub_strips_headers_and_markers(tmp_path):
    chapters = [(f"Chapter {i}",
                 f"{HEADER} (Chapter {i})</p><p>Body text {i}.[4] " + PARA)
                for i in range(1, 6)]
    epub = _make_epub(tmp_path, chapters)
    result = extract_epub(epub)
    qa = result["qa"]
    assert qa["epub_headers_removed"] >= 5
    assert qa["endnote_markers_stripped"] >= 5
    assert qa["epub_header_pattern"].startswith(HEADER[:15])
    for s in result["sections"]:
        assert HEADER not in s["body"]
        assert "[4]" not in s["body"]
        assert "Body text" in s["body"]


def test_extract_epub_no_headers_unaffected(tmp_path):
    epub = _make_epub(tmp_path, [("One", PARA), ("Two", PARA2)])
    result = extract_epub(epub)
    assert result["qa"]["epub_header_pattern"] == ""
    assert result["qa"]["epub_headers_removed"] == 0
    assert any(PARA.split()[3] in s["body"] for s in result["sections"])


# ── fidelity mirrors the hygiene ──────────────────────────────────────────

def test_fidelity_hygiene_mirror_scores_one():
    source = {"ch1": _body("We Need an Army", PARA + "[3]", PARA2),
              "ch2": _body("Our Task", PARA2 + "[14]", PARA),
              "ch3": _body("Two Roads", PARA, PARA2),
              "ch4": _body("The New Army", PARA2, PARA)}
    # workdir = post-hygiene bodies (headers gone, markers gone)
    workdir = {
        "01_a": "\n\n".join([PARA, PARA2]),
        "02_b": "\n\n".join([PARA2, PARA]),
        "03_c": "\n\n".join([PARA, PARA2]),
        "04_d": "\n\n".join([PARA2, PARA]),
    }
    report = compare_chapters(source, workdir,
                              header_prefix=HEADER, strip_markers=True)
    assert all(c.similarity == 1.0 for c in report.chapters)
    assert report.total_dropped == 0
    assert report.status == "passed"


def test_fidelity_without_mirror_flags_the_gap():
    # sanity: raw comparison sees the headers/markers as differences
    source = {"ch1": _body("X", PARA + "[3]", PARA2)}
    workdir = {"01_a": "\n\n".join([PARA, PARA2])}
    raw = compare_chapters(source, workdir)
    mirrored = compare_chapters(source, workdir,
                                header_prefix=HEADER, strip_markers=True)
    assert mirrored.chapters[0].similarity > raw.chapters[0].similarity
    assert mirrored.chapters[0].similarity == 1.0


def test_apply_pipeline_hygiene_unit():
    text = f"{HEADER} (T)\n\nReal text here.[12]\n\nMore text."
    out = _apply_pipeline_hygiene(text, HEADER, True)
    assert HEADER not in out
    assert "[12]" not in out
    assert "Real text here." in out and "More text." in out
