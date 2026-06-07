
# Product Vision & Scope

## What this tool is

**vorpal** — a **first-class, general-purpose PDF → audiobook converter**: point it at
any book-shaped PDF — scanned paperback or born-digital — and get back a clean,
navigable `.m4b` audiobook with correct chapters, read in a consistent, high-quality
voice, with **nothing silently missing and nothing spurious read aloud**. (The name:
it's the blade for the jabberwocky of OCR noise, fake chapters, and robot monotone.)

The Firestone book is the founding test case, not the product. The product is the tool.

**The north star:** drop in *any* PDF — however badly scanned or pristinely digital —
and have a voice you actually want to listen to (yes, the anime-girl narrator) read it
to you coherently, expressively, end to end. v1 earns the "coherently, end to end";
expressiveness is the layer that comes after (see below).

## The one-sentence contract

> Every sentence of the book's body text is narrated exactly once, in order, in one
> consistent voice, under the correct chapter marker — and anything that isn't body text
> (headers, footnotes, page numbers, TOC, index, OCR noise) is never narrated.

Every design decision in [03-architecture.md](03-architecture.md) serves that contract.

## The second contract: coherent (then expressive) narration

The text contract above says *what* gets read; this one says *how it sounds*:

1. **Coherence (v1).** TTS calls must be segmented so the narration flows like one
   reader: chunks never split a sentence, prefer paragraph alignment, carry pause
   metadata (longer pauses at paragraph/section boundaries), and fill the engine's
   context window rather than feeding it crumbs — prosody resets at every chunk
   boundary, so fewer, better-shaped chunks beat many small ones. (The v0 voice-clone
   incoherence was exactly this failure: 120-char chunks + per-chunk randomness.)
2. **Expressiveness (post-v1).** Each paragraph (or run of n sentences) carries a
   `tone` flag — e.g. `neutral`, `somber`, `tense`, `wry`, `excited` — that
   tone-capable engines use to color the delivery. Tagging is an **optional LLM pass**
   over the chunked text (deterministic pipeline core, model-assisted edges — same
   philosophy as LLM-assisted OCR repair); books build fine without it, and engines
   that can't act on tone ignore it. The chunk schema carries the field from v1
   onward so no migration is ever needed.

## Target user & invocation

A single technical-ish user on a local machine. CLI-first:

```
vorpal build book.pdf                       # the whole pipeline, sane defaults
vorpal build book.pdf --voice bm_george --title "..." --author "..."
vorpal review book.pdf                      # inspect/adjust detected chapters, then resume
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
   engine interface so a better local or API engine — including expressive,
   character-style voices — can be plugged in later.
4. **A text-normalization layer for TTS** — numbers, roman numerals, abbreviations,
   citations, quotes, dashes — so the narration sounds like a narrator, not a screen
   reader. Chunking is prosody-aware (sentence-safe, paragraph-aligned, pause
   metadata, engine-context-sized) and every chunk carries a `tone` slot for the
   expressive layer.
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
  voices are consistent by construction. If voice variety is ever wanted — including the
  north star's character narrator — the path is *more curated voices / better expressive
  engines behind `TTSEngine`*, not cloning.
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
