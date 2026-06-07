"""Command-line interface.

Phase 0: same stage flow and workdir layout as v0 (an existing *_workdir
resumes unchanged), with the F5/voice-clone path removed. `audiobook build`
is the only subcommand for now; review/status arrive with the manifest in
later phases (docs/04-roadmap.md).

Usage:
    audiobook build book.pdf --title "Book Title" --author "Author Name"
    audiobook build book.pdf --voice bm_george

    # Page range (useful for testing):
    audiobook build book.pdf --end-page 20 --output test_run

    # Force redo a step:
    audiobook build book.pdf --redo-ocr
    audiobook build book.pdf --redo-clean
    audiobook build book.pdf --redo-tts
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

from . import __version__
from .extract import ocr_images, pdf_to_images
from .master import compile_m4b
from .segment import clean_raw_text, split_into_chapters
from .synth import tts_all_chapters
from .tts import KOKORO_VOICES, KokoroEngine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="audiobook",
        description="Convert a PDF to a navigable .m4b audiobook",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--version", action="version", version=f"audiobooker {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="Run the full PDF → .m4b pipeline")
    build.add_argument("pdf")
    build.add_argument("--title",   default="",  help="Audiobook title metadata")
    build.add_argument("--author",  default="",  help="Author metadata")
    build.add_argument("--headers", nargs="+", metavar="TEXT",
                       help="Running page headers to strip from OCR text")
    build.add_argument("--voice",   default="af_heart", choices=KOKORO_VOICES,
                       help="Kokoro voice (default: af_heart)")
    build.add_argument("--speed",   type=float, default=1.0,
                       help="Narration speed multiplier (default: 1.0)")
    build.add_argument("--output",  default=None)
    build.add_argument("--dpi",     type=int, default=300)
    build.add_argument("--start-page", type=int, default=0)
    build.add_argument("--end-page",   type=int, default=None)
    build.add_argument("--keep-temp",  action="store_true")
    build.add_argument("--redo-images", action="store_true")
    build.add_argument("--redo-ocr",    action="store_true")
    build.add_argument("--redo-clean",  action="store_true")
    build.add_argument("--redo-tts",    action="store_true",
                       help="Delete existing chapter WAVs and re-synthesise")
    return parser


def cmd_build(args) -> None:
    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        sys.exit(f"ERROR: File not found: {pdf_path}")

    output_stem  = args.output or pdf_path.stem
    work_dir     = Path(f"{output_stem}_workdir")
    images_dir   = work_dir / "images"
    audio_dir    = work_dir / "audio_chunks"
    chapters_dir = work_dir / "chapters"

    for d in [work_dir, images_dir, audio_dir, chapters_dir]:
        d.mkdir(parents=True, exist_ok=True)

    raw_path      = work_dir / "raw_ocr.txt"
    clean_path    = work_dir / "clean_text.txt"
    chapters_json = work_dir / "chapters.json"

    print("=" * 58)
    print(f"  PDF -> Audiobook Pipeline  (audiobooker {__version__})")
    print(f"  Input:  {pdf_path}")
    print(f"  Output: {output_stem}.m4b")
    print(f"  TTS:    Kokoro (voice: {args.voice}, speed: {args.speed})")
    if args.title:  print(f"  Title:  {args.title}")
    if args.author: print(f"  Author: {args.author}")
    print("=" * 58)

    # ── Resume detection ──────────────────────────────
    existing_images  = sorted(images_dir.glob("page_*.png"))
    existing_ch_wavs = sorted(chapters_dir.glob("chapter_*.wav"))

    if any([existing_images, raw_path.exists(), clean_path.exists(),
            chapters_json.exists(), existing_ch_wavs]):
        print("\n  Resuming from existing progress:")
        if existing_images:        print(f"    {len(existing_images)} page images")
        if raw_path.exists():      print(f"    raw_ocr.txt")
        if clean_path.exists():    print(f"    clean_text.txt")
        if chapters_json.exists(): print(f"    chapters.json")
        if existing_ch_wavs:       print(f"    {len(existing_ch_wavs)} chapter WAVs")
        print()

    # ── Step 1: PDF -> images ─────────────────────────
    if existing_images and not args.redo_images:
        print(f"[1/5] Skipping images — {len(existing_images)} exist  (--redo-images to force)")
        image_paths = existing_images
    else:
        image_paths = pdf_to_images(pdf_path, images_dir, args.dpi,
                                    args.start_page, args.end_page)

    # ── Step 2: OCR ───────────────────────────────────
    if raw_path.exists() and not args.redo_ocr:
        print(f"[2/5] Skipping OCR — raw_ocr.txt exists  (--redo-ocr to force)")
        raw_text = raw_path.read_text(encoding="utf-8")
    else:
        raw_text = ocr_images(image_paths)
        raw_path.write_text(raw_text, encoding="utf-8")

    # ── Step 3: Clean + chapter split ─────────────────
    if chapters_json.exists() and not args.redo_clean:
        print(f"[3/5] Skipping clean/split — chapters.json exists  (--redo-clean to force)")
        chapters = json.loads(chapters_json.read_text(encoding="utf-8"))
    else:
        print(f"\n[3/5] Cleaning text and detecting chapters...")
        clean = clean_raw_text(raw_text, args.headers)
        clean_path.write_text(clean, encoding="utf-8")
        chapters = split_into_chapters(clean)
        chapters_json.write_text(json.dumps(chapters, indent=2, ensure_ascii=False),
                                 encoding="utf-8")
        print(f"  Saved: clean_text.txt  and  chapters.json")
        print(f"  TIP: Edit chapters.json to fix chapter titles or set skip=true/false,")
        print(f"       then re-run with --redo-tts to regenerate audio only.")

    # ── Step 4: TTS ───────────────────────────────────
    if args.redo_tts and chapters_dir.exists():
        print("  --redo-tts: removing existing chapter WAVs...")
        for f in chapters_dir.glob("chapter_*.wav"):
            f.unlink()
        for f in audio_dir.glob("*.wav"):
            f.unlink()

    engine = KokoroEngine(voice=args.voice, speed=args.speed)
    chapter_results = tts_all_chapters(chapters, audio_dir, chapters_dir, engine)

    if not chapter_results:
        sys.exit("ERROR: No audio generated.")

    # ── Step 5: Compile M4B ───────────────────────────
    final = compile_m4b(
        chapter_results, output_stem,
        title=args.title or pdf_path.stem,
        author=args.author,
    )

    if not args.keep_temp:
        shutil.rmtree(images_dir, ignore_errors=True)
        shutil.rmtree(audio_dir,  ignore_errors=True)

    print("\n" + "=" * 58)
    print(f"  Done!  ->  {final}")
    print(f"  Work files: {work_dir}/")
    print("=" * 58)


def main(argv=None) -> None:
    # Progress output uses unicode (em-dashes, bars); don't crash on legacy
    # Windows console codepages (e.g. cp932) — degrade to replacement chars.
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    args = build_parser().parse_args(argv)
    if args.command == "build":
        cmd_build(args)


if __name__ == "__main__":
    main()
