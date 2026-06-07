"""Command-line interface.

Usage:
    vorpal build book.pdf --title "Book Title" --author "Author Name"
    vorpal build book.pdf --voice bm_george

    # Inspect / adjust detected chapters, then approve:
    vorpal review book.pdf
    vorpal review book.pdf --approve

    # Page range (useful for testing):
    vorpal build book.pdf --end-page 20 --output test_run

    # Force redo a step:
    vorpal build book.pdf --redo-ocr
    vorpal build book.pdf --redo-segment
    vorpal build book.pdf --redo-tts
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

from . import __version__
from .extract import extract_pages, pages_to_flat_text, read_pages_jsonl, write_pages_jsonl
from .extract.epub import extract_epub
from .extract.text import extract_txt
from .ingest import ingest, detect_format
from .manifest import Manifest, hash_parts
from .binaries import MissingBinaryError
from .master import compile_m4b
from .segment import Section, section_body, segment_pages
from .synth import safe_filename, tts_all_chapters
from .tts import KOKORO_VOICES, KokoroEngine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vorpal",
        description="Convert a PDF to a navigable .m4b audiobook",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--version", action="version", version=f"vorpal {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="Run the full PDF/EPUB/TXT → .m4b pipeline")
    build.add_argument("input", help="Input file: PDF, EPUB, or plain-text (.txt)")
    build.add_argument("--title",   default="",  help="Audiobook title metadata")
    build.add_argument("--author",  default="",  help="Author metadata")
    build.add_argument("--voice",   default="af_heart", choices=KOKORO_VOICES,
                       help="Kokoro voice (default: af_heart)")
    build.add_argument("--speed",   type=float, default=1.0,
                       help="Narration speed multiplier (default: 1.0)")
    build.add_argument("--output",  default=None)
    build.add_argument("--dpi",     type=int, default=300)
    build.add_argument("--start-page", type=int, default=0)
    build.add_argument("--end-page",   type=int, default=None)
    build.add_argument("--keep-temp",  action="store_true")
    build.add_argument("--redo-extract", "--redo-ocr", "--redo-images",
                       dest="redo_extract", action="store_true",
                       help="Force re-extraction (rasterize/OCR) of all pages")
    build.add_argument("--redo-segment", "--redo-clean", dest="redo_segment",
                       action="store_true",
                       help="Force re-segmentation / re-parse (boilerplate/chapters/EPUB spine)")
    build.add_argument("--redo-tts",    action="store_true",
                       help="Delete existing chapter WAVs and re-synthesise")
    build.add_argument("--allow-gaps", action="store_true",
                       help="Insert audible beep markers for failed chunks instead of aborting")
    build.add_argument("--stop-after", choices=["extract", "segment"], default=None,
                       help="Stop the build after the named stage (inspection runs)")

    review = sub.add_parser("review",
                            help="Inspect detected chapters; edit book.json; approve")
    review.add_argument("input", help="Input file that was built (PDF, EPUB, or TXT)")
    review.add_argument("--output", default=None,
                        help="Workdir stem if it differs from the input file name")
    review.add_argument("--approve", action="store_true",
                        help="Mark the chapter list as approved for synthesis")
    return parser


# ── review table ──────────────────────────────────────────────────────────

def print_section_table(sections: list, qa: dict = None) -> None:
    print(f"\n  {'id':>3} {'kind':<11} {'incl':<5} {'src':<9} {'conf':<5} "
          f"{'pages':<9} {'words':>7}  title")
    print("  " + "─" * 88)
    for s in sections:
        flags = f"  [{', '.join(s.flags)}]" if s.flags else ""
        pages = f"{s.start[0] + 1}-{s.end[0] + 1}" if s.end else str(s.start[0] + 1)
        print(f"  {s.id:>3} {s.kind:<11} {str(s.include):<5} {s.source:<9} "
              f"{s.confidence:<5.2f} {pages:<9} {s.words:>7}  {s.title[:46]}{flags}")
    if qa and qa.get("pages_flagged"):
        print(f"\n  Flagged pages (figures / low OCR quality): {qa['pages_flagged']}")


def needs_review(sections: list) -> bool:
    """Build pauses for review unless every narrated section came from a
    trusted source with no validation flags.

    Trusted sources: outline (PDF embedded), toc (printed TOC),
    spine (EPUB spine — ground truth by definition for EPUB input).
    """
    for s in sections:
        if not s.include:
            continue
        if s.source not in ("outline", "toc", "spine") or s.flags:
            return True
    return False


def cmd_build(args) -> None:
    input_path = Path(args.input)
    if not input_path.exists():
        sys.exit(f"ERROR: File not found: {input_path}")

    try:
        fmt = detect_format(input_path)
    except ValueError as e:
        sys.exit(f"ERROR: {e}")

    output_stem  = args.output or input_path.stem
    work_dir     = Path(f"{output_stem}_workdir")
    audio_dir    = work_dir / "audio_chunks"
    chapters_dir = work_dir / "chapters"

    for d in [work_dir, audio_dir, chapters_dir]:
        d.mkdir(parents=True, exist_ok=True)

    pages_path     = work_dir / "pages.jsonl"
    raw_path       = work_dir / "raw_ocr.txt"          # flat debug view
    seg_pages_path = work_dir / "pages_segmented.jsonl"
    footnotes_path = work_dir / "footnotes.json"

    fmt_label = {"pdf": "PDF", "epub": "EPUB", "txt": "TXT"}[fmt]
    print("=" * 58)
    print(f"  {fmt_label} -> Audiobook Pipeline  (vorpal {__version__})")
    print(f"  Input:  {input_path}")
    print(f"  Output: {output_stem}.m4b")
    print(f"  TTS:    Kokoro (voice: {args.voice}, speed: {args.speed})")
    if args.title:  print(f"  Title:  {args.title}")
    if args.author: print(f"  Author: {args.author}")
    print("=" * 58)

    manifest = Manifest.load_or_create(work_dir)

    # ── Step 1: Ingest (probe source file) ───────────
    ingest(input_path, manifest)

    # Fall back to source metadata for title/author when flags are omitted
    title  = args.title or manifest.source.get("title") or input_path.stem
    author = args.author or manifest.source.get("author") or ""

    # ── Steps 2–3: Format dispatch ───────────────────
    if fmt == "pdf":
        sections, seg_pages = _build_pdf_stages(
            args, input_path, manifest,
            pages_path, raw_path, seg_pages_path, footnotes_path,
            work_dir,
        )
        pdf_path_for_cover = input_path
    else:
        sections, seg_pages = _build_format_parse(
            args, input_path, fmt, manifest, work_dir,
        )
        # Update title/author from what the parser found (EPUB/TXT metadata)
        title  = args.title or manifest.source.get("title") or input_path.stem
        author = args.author or manifest.source.get("author") or ""
        pdf_path_for_cover = None

    if args.stop_after == "segment":
        body_dir = work_dir / "chapter_texts"
        body_dir.mkdir(exist_ok=True)
        for s in sections:
            if s.include:
                body = section_body(s, seg_pages)
                (body_dir / f"{s.id:02d}_{safe_filename(s.title)}.txt").write_text(
                    body, encoding="utf-8")
        print(f"\n  --stop-after segment: chapter texts in {body_dir}/")
        return

    # ── Review gate ───────────────────────────────────
    review_status = manifest.stage("review").get("status")
    if review_status not in ("approved", "auto-approved"):
        if needs_review(sections):
            out_flag = f" --output {args.output}" if args.output else ""
            print_section_table(sections, manifest.qa)
            print(f"\n  Chapter detection needs review.")
            print(f"  Edit chapters in: {manifest.path}")
            print(f"  (title / include / spoken_intro / start / end), then run:")
            sys.exit(f"      vorpal review {args.input}{out_flag} --approve")
        manifest.data["stages"]["review"] = {"status": "auto-approved"}
        manifest.save()
        print(f"  Review auto-approved "
              f"(all chapters from a trusted source, no flags)")

    # Regenerate narrated bodies from the (possibly user-edited) manifest.
    # For PDF: boundaries are block-level references into pages_segmented.jsonl.
    # For EPUB/TXT: bodies are stored inline on each section.
    sections = [Section.from_dict(d) for d in manifest.data["chapters"]]
    body_dir = work_dir / "chapter_texts"
    body_dir.mkdir(exist_ok=True)
    chapters = []
    for s in sections:
        body = section_body(s, seg_pages)
        if s.include:
            (body_dir / f"{s.id:02d}_{safe_filename(s.title)}.txt").write_text(
                body, encoding="utf-8")
        chapters.append({"title": s.title, "body": body, "skip": not s.include,
                         "spoken_intro": s.spoken_intro})

    # ── Step 4: TTS ───────────────────────────────────
    if args.redo_tts and chapters_dir.exists():
        print("  --redo-tts: removing existing chapter WAVs...")
        for f in chapters_dir.glob("chapter_*.wav"):
            f.unlink()
        for f in audio_dir.glob("*.wav"):
            f.unlink()

    engine = KokoroEngine(voice=args.voice, speed=args.speed)
    chapter_results, synth_report = tts_all_chapters(
        chapters, audio_dir, chapters_dir, engine,
        allow_gaps=getattr(args, "allow_gaps", False),
    )

    if not chapter_results:
        sys.exit("ERROR: No audio generated.")

    # ── Step 5: Mastering & packaging ─────────────────
    settings = manifest.settings
    target_lufs = float(settings.get("target_lufs", -18.0))
    silence_ms  = int(settings.get("inter_chapter_silence_ms", 1500))
    aac_bitrate = str(settings.get("aac_bitrate", "64k"))

    try:
        final = compile_m4b(
            chapter_results, output_stem,
            title=title,
            author=author,
            target_lufs=target_lufs,
            inter_chapter_silence_ms=silence_ms,
            aac_bitrate=aac_bitrate,
            pdf_path=pdf_path_for_cover,
            work_dir=work_dir,
            synth_report=synth_report,
            manifest_qa=manifest.qa,
        )
    except MissingBinaryError as e:
        sys.exit(f"ERROR: {e}")

    if not args.keep_temp:
        shutil.rmtree(audio_dir, ignore_errors=True)

    print("\n" + "=" * 58)
    print(f"  Done!  ->  {final}")
    print(f"  Work files: {work_dir}/")
    print("=" * 58)


# ── format-specific pipeline stages ──────────────────────────────────────

def _build_pdf_stages(args, pdf_path, manifest, pages_path, raw_path,
                      seg_pages_path, footnotes_path, work_dir):
    """Run extract + segment stages for PDF input.  Returns (sections, seg_pages)."""
    extract_hash = hash_parts(
        "extract-v1", manifest.source["sha256"],
        args.dpi, args.start_page, args.end_page or 0,
    )
    extract_ran = False
    if manifest.stage_fresh("extract", extract_hash) and not args.redo_extract:
        print(f"[2/5] Extraction fresh — reusing pages.jsonl  (--redo-extract to force)")
        pages = read_pages_jsonl(pages_path)
    else:
        pages = extract_pages(pdf_path, manifest.data["pages"], dpi=args.dpi,
                              start_page=args.start_page, end_page=args.end_page)
        write_pages_jsonl(pages, pages_path)
        raw_path.write_text(pages_to_flat_text(pages), encoding="utf-8")
        scanned = [p for p in pages if p.kind == "scanned" and p.blocks]
        manifest.qa["pages_flagged"] = [p.index for p in pages if p.flagged]
        manifest.qa["mean_ocr_confidence"] = (
            round(sum(p.conf for p in scanned) / len(scanned), 4) if scanned else None
        )
        manifest.stage_done("extract", extract_hash, artifact="pages.jsonl")
        extract_ran = True

    if args.stop_after == "extract":
        print("\n  --stop-after extract: done.")
        sys.exit(0)

    segment_hash = hash_parts("segment-v2", extract_hash)
    if manifest.stage_fresh("segment", segment_hash) and not args.redo_segment \
            and not extract_ran:
        print(f"[3/5] Segmentation fresh — reusing chapter list  (--redo-segment to force)")
        seg_pages = read_pages_jsonl(seg_pages_path)
        sections = [Section.from_dict(d) for d in manifest.data["chapters"]]
    else:
        print(f"\n[3/5] Segmenting (boilerplate, footnotes, repair, chapters)...")
        seg_pages = pages
        result = segment_pages(seg_pages, outline=manifest.source.get("outline"))
        write_pages_jsonl(seg_pages, seg_pages_path)
        footnotes_path.write_text(
            json.dumps(result.footnotes, indent=2, ensure_ascii=False),
            encoding="utf-8")
        sections = result.sections
        manifest.data["chapters"] = [s.to_dict() for s in sections]
        manifest.qa.update(result.qa)
        manifest.stage_done("segment", segment_hash, artifact="pages_segmented.jsonl")
        manifest.data["stages"].pop("review", None)
        manifest.save()
        print(f"  Chapter source: {result.source}  |  "
              f"headers removed: {result.qa['header_lines_removed']}  |  "
              f"footnotes: {result.qa['footnotes_separated']}")
        print_section_table(sections, manifest.qa)

    return sections, seg_pages


def _build_format_parse(args, input_path, fmt, manifest, work_dir):
    """Run the single 'parse' stage for EPUB/TXT input.  Returns (sections, [])."""
    parse_hash = hash_parts("parse-v1", manifest.source["sha256"], fmt)

    if manifest.stage_fresh("parse", parse_hash) and not args.redo_segment:
        print(f"[2/5] Parse fresh — reusing chapter list  (--redo-segment to force)")
        sections = [Section.from_dict(d) for d in manifest.data["chapters"]]
        return sections, []

    if fmt == "epub":
        print(f"\n[2/5] Parsing EPUB spine & TOC...")
        result = extract_epub(input_path)
    else:
        print(f"\n[2/5] Parsing TXT chapter headings...")
        result = extract_txt(input_path)

    # Populate manifest fields from parser result
    manifest.source["title"] = result.get("title") or manifest.source.get("title", "")
    manifest.source["author"] = result.get("author") or manifest.source.get("author", "")
    sections = [Section.from_dict(d) for d in result["sections"]]
    manifest.data["chapters"] = [s.to_dict() for s in sections]
    manifest.qa.update(result.get("qa", {}))
    manifest.stage_done("parse", parse_hash)
    manifest.data["stages"].pop("review", None)
    manifest.save()

    n_chapters = sum(1 for s in sections if s.include)
    print(f"  Source: {fmt}  |  sections: {len(sections)}  |  narrated: {n_chapters}")
    print_section_table(sections, manifest.qa)

    return sections, []


def cmd_review(args) -> None:
    input_path = Path(args.input)
    output_stem = args.output or input_path.stem
    work_dir = Path(f"{output_stem}_workdir")
    manifest_path = work_dir / "book.json"
    if not manifest_path.exists():
        sys.exit(f"ERROR: No manifest at {manifest_path} — run `vorpal build` first.")

    manifest = Manifest.load_or_create(work_dir)
    sections = [Section.from_dict(d) for d in manifest.data.get("chapters", [])]
    if not sections:
        sys.exit("ERROR: No chapters in the manifest — run `vorpal build` first.")

    print(f"  Chapters detected for: {manifest.source.get('title') or input_path.name}")
    print_section_table(sections, manifest.qa)

    out_flag = f" --output {args.output}" if args.output else ""
    if args.approve:
        manifest.data["stages"]["review"] = {"status": "approved"}
        manifest.save()
        print(f"\n  Approved. Run `vorpal build {args.input}{out_flag}` to continue.")
    else:
        status = manifest.stage("review").get("status", "pending")
        print(f"\n  Review status: {status}")
        print(f"  To adjust: edit `chapters` in {manifest_path}")
        print(f"  (title / include / spoken_intro / start / end blocks), then:")
        print(f"      vorpal review {args.input}{out_flag} --approve")


def main(argv=None) -> None:
    # Progress output uses unicode (em-dashes, bars); don't crash on legacy
    # Windows console codepages (e.g. cp932) — degrade to replacement chars.
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    args = build_parser().parse_args(argv)
    if args.command == "build":
        cmd_build(args)
    elif args.command == "review":
        cmd_review(args)


if __name__ == "__main__":
    main()
