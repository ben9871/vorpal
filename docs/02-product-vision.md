# Product Vision & Scope

## What this tool is

A **first-class, general-purpose PDF → audiobook converter**: point it at any book-shaped
PDF — scanned paperback or born-digital — and get back a clean, navigable `.m4b`
audiobook with correct chapters, read in a consistent, high-quality voice, with **nothing
silently missing and nothing spurious read aloud**.

The Firestone book is the founding test case, not the product. The product is the tool.

## The one-sentence contract

> Every sentence of the book's body text is narrated exactly once, in order, in one
> consistent voice, under the correct chapter marker — and anything that isn't body text
> (headers, footnotes, page numbers, TOC, index, OCR noise) is never narrated.

Every design decision in [03-architecture.md](03-architecture.md) serves that contract.

## Target user & invocation

A single technical-ish user on a local machine. CLI-first:

```
audiobook build book.pdf                       # the whole pipeline, sane defaults
audiobook build book.pdf --voice bm_george --title "..." --author "..."
audiobook review book.pdf                      # inspect/adjust detected chapters, then resume
```

One command should do the right thing for the common case; the review checkpoint exists
because chapter detection on messy scans can never be 100% — the tool must make human
correction *cheap* (edit one small file, re-run, only affected work redone).

## In scope

1. **Both PDF species, detected automatically per page:**
   - *Born-digital* — extract the embedded text layer directly (fast, lossless).
   - *Scanned* — preprocess images and OCR, with per-page quality scoring and targeted
     re-OCR of bad pages.
2. **Real document understanding:** running header/footer removal by cross-page
   repetition, footnote separation, hyphenation repair, front/back-matter classification,
   chapter detection that consults the PDF outline and the printed TOC before falling
   back to heuristics.
3. **TTS with curated standard voices** (Kokoro as the default engine), behind a small
   engine interface so a better local or API engine can be plugged in later.
4. **A text-normalization layer for TTS** — numbers, roman numerals, abbreviations,
   citations, quotes, dashes — so the narration sounds like a narrator, not a screen
   reader.
5. **Proper audiobook mastering:** loudness-normalized chapters, streaming assembly
   (constant memory), `.m4b` with chapter markers, metadata, and cover art; per-chapter
   MP3s kept as a side product.
6. **Resumability and reproducibility:** a manifest with content hashes; any stage can be
   redone in isolation; nothing stale is ever silently reused.
7. **Quality gates at every stage** — see the QA section of the architecture doc. The
   pipeline fails loudly with an actionable report rather than producing a quietly broken
   audiobook.

## Explicitly out of scope

- **Voice cloning.** The F5-TTS `--voice-ref` path is removed, not fixed. The audit
  ([01-audit.md](01-audit.md) §3) shows the incoherence was structural (per-chunk random
  seeds, 8-second context windows, noisy reference audio), and even a repaired
  implementation trades away the consistency that defines a listenable audiobook. Curated
  voices are consistent by construction. If voice variety is ever wanted, the path is
  *more curated voices / better engines*, not cloning.
- **Non-PDF inputs** (EPUB, DOCX, web). The architecture keeps extraction behind one
  interface so EPUB could be added later, but it is not part of this effort.
- **GUI / server / multi-user anything.** Local CLI tool.
- **DRM circumvention.** Input is assumed to be a PDF the user lawfully possesses.
- **Multi-voice dramatization, music beds, sound effects.** One narrator voice per book.

## Quality bar (acceptance, at the product level)

The tool is "first class" when, on the regression set (Firestone scan + at least one
born-digital PDF + one outline-less digital PDF):

1. Detected chapter list matches the book's actual TOC (after at most a one-file,
   sub-minute human review step).
2. Zero running headers, page numbers, footnote markers, or OCR junk lines in the
   narrated text (spot-checked + lint rules).
3. Zero silently dropped sentences — synthesis failures either recover or abort the build
   with a report naming the exact text.
4. Audio is loudness-consistent across chapters (±1 LU), one voice throughout, chapter
   markers land exactly at chapter starts.
5. A fresh clone of the repo + `pip install` + one command reproduces the build on
   Windows (primary) without editing source code.

## Why not "just use an existing tool"

Existing open-source converters assume clean text input or do naive per-page OCR dumps —
exactly the failure mode the audit documents. The differentiating work here is the
*middle* of the pipeline (document understanding + TTS normalization + QA gates), which
is where the current implementation failed and where commodity tools are weakest. The
edges (PyMuPDF, Tesseract, Kokoro, ffmpeg) are solved problems we compose, not rebuild.
