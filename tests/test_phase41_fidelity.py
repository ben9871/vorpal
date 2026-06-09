"""Phase 41: text fidelity tooling (vorpal/qa/fidelity.py + `vorpal fidelity`)."""

import io
import zipfile

import pytest

from vorpal.cli import build_parser
from vorpal.qa.fidelity import (
    ChapterFidelity,
    FidelityReport,
    compare_chapters,
    extract_epub_chapter_texts,
    extract_source_texts,
    extract_txt_chapter_texts,
    extract_workdir_chapter_texts,
    format_fidelity_report,
    run_fidelity_check,
    _best_span,
    _norm_words,
)


# ── fixtures ──────────────────────────────────────────────────────────────

PARA = ("The army of the revolution requires discipline above all things, "
        "and discipline rests upon trust in the command staff.")
PARA2 = ("Every soldier of the workers and peasants must understand why the "
         "struggle is being waged and what its outcome will decide.")
PARA3 = ("The railways are the arteries of the front, and without transport "
         "no operation can be sustained for even a single week.")


def _chapter_text(*paras):
    return "\n\n".join(paras)


def _write_workdir(tmp_path, chapters):
    """chapters: [(filename_stem, text), ...] → workdir path."""
    body_dir = tmp_path / "chapter_texts"
    body_dir.mkdir(parents=True, exist_ok=True)
    for stem, text in chapters:
        (body_dir / f"{stem}.txt").write_text(text, encoding="utf-8")
    return tmp_path


def _make_epub(tmp_path, chapters, title="Test Book"):
    """chapters: [(title, html_body), ...] → epub path (minimal valid EPUB3)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", """\
<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:schemas:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>""")
        spine_items = []
        for i, (ch_title, ch_body) in enumerate(chapters):
            fname = f"OEBPS/ch{i+1:02d}.xhtml"
            spine_items.append((f"ch{i+1:02d}", fname))
            zf.writestr(fname, f"""\
<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>{ch_title}</title></head>
<body><h1>{ch_title}</h1><p>{ch_body}</p></body>
</html>""")
        nav = ('<?xml version="1.0" encoding="utf-8"?>'
               '<html xmlns="http://www.w3.org/1999/xhtml"'
               ' xmlns:epub="http://www.idpf.org/2007/ops">'
               '<body><nav epub:type="toc"><ol>')
        for (item_id, fname), (ch_title, _) in zip(spine_items, chapters):
            nav += f'<li><a href="{fname[6:]}">{ch_title}</a></li>'
        nav += '</ol></nav></body></html>'
        zf.writestr("OEBPS/nav.xhtml", nav)
        items = "\n".join(
            f'<item id="{iid}" href="{fn[6:]}" media-type="application/xhtml+xml"/>'
            for iid, fn in spine_items)
        refs = "\n".join(f'<itemref idref="{iid}"/>' for iid, _ in spine_items)
        zf.writestr("OEBPS/content.opf", f"""\
<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="uid">test-id</dc:identifier>
    <dc:title>{title}</dc:title>
    <dc:language>en</dc:language>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    {items}
  </manifest>
  <spine>{refs}</spine>
</package>""")
    path = tmp_path / "book.epub"
    path.write_bytes(buf.getvalue())
    return path


# ── similarity scoring ────────────────────────────────────────────────────

def test_identical_text_scores_one():
    source = {"ch1": _chapter_text(PARA, PARA2)}
    workdir = {"01_chapter": _chapter_text(PARA, PARA2)}
    report = compare_chapters(source, workdir)
    assert report.chapters[0].similarity == 1.0
    assert report.status == "passed"


def test_unrelated_text_scores_low_and_fails():
    source = {"ch1": _chapter_text(PARA, PARA2, PARA3)}
    workdir = {"01_chapter": "Completely different words about gardening "
                             "and the cultivation of ornamental roses."}
    report = compare_chapters(source, workdir)
    assert report.chapters[0].similarity < 0.70
    assert report.status == "failed"


def test_partial_loss_is_degraded():
    # ~20% of source words missing → ratio in the degraded band
    source = {"ch1": _chapter_text(PARA, PARA2, PARA3, PARA, PARA2)}
    workdir = {"01_chapter": _chapter_text(PARA, PARA2, PARA3, PARA)}
    report = compare_chapters(source, workdir)
    sim = report.chapters[0].similarity
    assert 0.70 <= sim < 0.95
    assert report.status in ("degraded", "passed")  # band depends on rounding
    # the specific fixture should land below the pass threshold
    assert report.status == "degraded"


def test_punctuation_and_case_do_not_matter():
    source = {"ch1": PARA}
    workdir = {"01_x": PARA.upper().replace(",", " ,")}
    report = compare_chapters(source, workdir)
    assert report.chapters[0].similarity == 1.0


# ── dropped paragraph detection ───────────────────────────────────────────

def test_dropped_paragraph_detected():
    source = {"ch1": _chapter_text(PARA, PARA2, PARA3)}
    workdir = {"01_chapter": _chapter_text(PARA, PARA3)}  # PARA2 dropped
    report = compare_chapters(source, workdir)
    ch = report.chapters[0]
    assert len(ch.dropped_paragraphs) == 1
    assert "Every soldier" in ch.dropped_paragraphs[0]


def test_no_false_drop_when_text_present():
    source = {"ch1": _chapter_text(PARA, PARA2)}
    workdir = {"01_chapter": _chapter_text(PARA, PARA2)}
    report = compare_chapters(source, workdir)
    assert report.chapters[0].dropped_paragraphs == []


def test_short_paragraphs_not_counted_as_drops():
    source = {"ch1": _chapter_text(PARA, "Chapter II", "1918.")}
    workdir = {"01_chapter": PARA}
    report = compare_chapters(source, workdir)
    assert report.chapters[0].dropped_paragraphs == []


def test_paragraph_present_in_other_chapter_not_a_drop():
    # Paragraph moved across a chapter boundary is not "dropped"
    source = {"ch1": _chapter_text(PARA, PARA2), "ch2": PARA3}
    workdir = {"01_a": PARA, "02_b": _chapter_text(PARA2, PARA3)}
    report = compare_chapters(source, workdir)
    assert report.total_dropped == 0


# ── alignment (merged spine items, order) ─────────────────────────────────

def test_merged_spine_items_match_one_chapter():
    # EPUB sections legitimately merge untitled spine items
    source = {"ch1": PARA, "ch2": PARA2, "ch3": PARA3}
    workdir = {"01_merged": _chapter_text(PARA, PARA2), "02_c": PARA3}
    report = compare_chapters(source, workdir)
    first = report.chapters[0]
    assert first.matched_source == ["ch1", "ch2"]
    assert first.similarity >= 0.99
    assert report.status == "passed"
    assert report.unmatched_source == []


def test_order_anomaly_detected():
    source = {"ch1": PARA, "ch2": PARA2}
    # workdir narrates ch2 before ch1
    workdir = {"01_first": PARA2, "02_second": PARA}
    report = compare_chapters(source, workdir)
    assert len(report.order_anomalies) == 1
    assert "02_second" in report.order_anomalies[0]


def test_in_order_chapters_no_anomaly():
    source = {"ch1": PARA, "ch2": PARA2, "ch3": PARA3}
    workdir = {"01_a": PARA, "02_b": PARA2, "03_c": PARA3}
    report = compare_chapters(source, workdir)
    assert report.order_anomalies == []


def test_unmatched_source_items_listed():
    # front/backmatter excluded from narration shows up as unmatched
    source = {"cover": "Cover page text that is long enough to be an item "
                       "with several words inside it for matching purposes",
              "ch1": PARA, "license": PARA3}
    workdir = {"01_a": PARA}
    report = compare_chapters(source, workdir)
    assert "cover" in report.unmatched_source
    assert "license" in report.unmatched_source
    assert "ch1" not in report.unmatched_source


# ── edge cases ────────────────────────────────────────────────────────────

def test_empty_workdir_fails():
    source = {"ch1": PARA}
    report = compare_chapters(source, {})
    assert report.chapters == []
    assert report.status == "failed"
    assert report.unmatched_source == ["ch1"]


def test_empty_source_items_skipped():
    source = {"blank": "   ", "ch1": PARA}
    workdir = {"01_a": PARA}
    report = compare_chapters(source, workdir)
    assert report.chapters[0].matched_source == ["ch1"]
    assert report.status == "passed"


def test_extract_workdir_missing_dir_returns_empty(tmp_path):
    assert extract_workdir_chapter_texts(tmp_path) == {}


def test_extract_workdir_reads_in_filename_order(tmp_path):
    wd = _write_workdir(tmp_path, [("02_b", "second"), ("01_a", "first")])
    texts = extract_workdir_chapter_texts(wd)
    assert list(texts) == ["01_a", "02_b"]
    assert texts["01_a"] == "first"


def test_norm_words_strips_punctuation():
    assert _norm_words("Hello, World! It's 1918.") == \
        ["hello", "world", "it's", "1918"]


def test_best_span_empty_source():
    sim, span = _best_span([], {}, ["some", "words"])
    assert sim == 0.0 and span == []


# ── EPUB source extraction ────────────────────────────────────────────────

def test_extract_epub_chapter_texts(tmp_path):
    epub = _make_epub(tmp_path, [("One", PARA), ("Two", PARA2)])
    texts = extract_epub_chapter_texts(epub)
    assert len(texts) == 2
    vals = list(texts.values())
    assert "discipline" in vals[0]
    assert "Every soldier" in vals[1]


def test_extract_source_texts_dispatch(tmp_path):
    txt = tmp_path / "book.txt"
    txt.write_text(PARA, encoding="utf-8")
    assert PARA in list(extract_txt_chapter_texts(txt).values())[0]
    assert PARA in list(extract_source_texts(txt).values())[0]
    with pytest.raises(ValueError):
        extract_source_texts(tmp_path / "book.docx")


def test_run_fidelity_check_end_to_end(tmp_path):
    # The pipeline's EPUB path uses the same HTML→text extractor, so a
    # faithful build's chapter bodies equal the extracted spine texts.
    epub = _make_epub(tmp_path, [("One", PARA), ("Two", PARA2)])
    spine_texts = list(extract_epub_chapter_texts(epub).values())
    wd = _write_workdir(tmp_path / "wd", [("01_one", spine_texts[0]),
                                          ("02_two", spine_texts[1])])
    report = run_fidelity_check(epub, wd)
    assert report.status == "passed"
    assert len(report.chapters) == 2
    assert all(c.similarity == 1.0 for c in report.chapters)


# ── report rendering ──────────────────────────────────────────────────────

def test_format_report_contains_table_and_status():
    report = compare_chapters({"ch1": PARA}, {"01_a": PARA})
    text = format_fidelity_report(report, "src.epub", "wd")
    assert "| Chapter |" in text
    assert "01_a" in text
    assert "PASSED" in text
    assert "src.epub" in text


def test_format_report_empty_workdir():
    report = compare_chapters({"ch1": PARA}, {})
    text = format_fidelity_report(report)
    assert "No chapter texts found" in text
    assert "FAILED" in text


def test_format_report_lists_drops_and_anomalies():
    source = {"ch1": _chapter_text(PARA, PARA2), "ch2": PARA3}
    workdir = {"01_a": PARA3, "02_b": PARA}  # out of order + PARA2 dropped
    report = compare_chapters(source, workdir)
    text = format_fidelity_report(report)
    assert "Dropped paragraphs" in text
    assert "Order anomalies" in text


# ── findings from the Trotsky pre-flight audit ────────────────────────────

def test_backward_extension_catches_leading_stub():
    # EPUB split files: tiny title-page stub merged before the chapter body.
    # Forward-only extension never matched the stub (its quick_ratio is too
    # low to be a start candidate), depressing the chapter's similarity.
    stub = "Volume Two Problems of Building the Army part one"
    source = {"ch04_split_000": stub, "ch04_split_001": _chapter_text(PARA, PARA2, PARA3)}
    workdir = {"04_chapter": _chapter_text(stub, PARA, PARA2, PARA3)}
    report = compare_chapters(source, workdir)
    ch = report.chapters[0]
    assert ch.matched_source == ["ch04_split_000", "ch04_split_001"]
    assert ch.similarity == 1.0
    assert report.unmatched_source == []


def test_about_titled_chapters_are_chapters():
    # Phase 41 audit: "about " backmatter prefix swallowed real Trotsky
    # chapters in v1 (ch20, ch23) and v3 (ch17, ch37).
    from vorpal.extract.epub import _classify_title as classify_epub
    from vorpal.extract.text import _classify_title as classify_txt
    for classify in (classify_epub, classify_txt):
        assert classify("About the ex-Officers") == "chapter"
        assert classify("About the officers deceived by Krasnov") == "chapter"
        assert classify("About the Organisation of Labour") == "chapter"
        assert classify("About Bonar Law's Speech") == "chapter"
        # publisher/edition material still classified out of the narration
        assert classify("About the Author") == "frontmatter"
        assert classify("About the Publisher") == "backmatter"
        assert classify("About This Edition") == "backmatter"


# ── CLI surface ───────────────────────────────────────────────────────────

def test_cli_fidelity_subcommand_parses():
    parser = build_parser()
    args = parser.parse_args(["fidelity", "book.epub", "book_workdir"])
    assert args.command == "fidelity"
    assert args.source == "book.epub"
    assert args.workdir == "book_workdir"
    assert args.output is None


def test_cli_fidelity_output_flag():
    parser = build_parser()
    args = parser.parse_args(
        ["fidelity", "b.epub", "wd", "--output", "report.md"])
    assert args.output == "report.md"


def test_build_parser_surface_unchanged():
    # `vorpal build` must be unaffected by the new subcommand
    parser = build_parser()
    args = parser.parse_args(["build", "x.pdf"])
    assert args.command == "build"
