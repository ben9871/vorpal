# Pipeline Architecture

vorpal's pipeline is **manifest-driven** and **content-addressed**. Every stage
reads from and writes to a single JSON manifest (`book.json`). A stage re-runs
only when its inputs have changed — identified by content hash, not timestamp.

## The manifest

`book.json` lives in the workdir (`<output>_workdir/`). It records:

- Source file metadata (path, format, SHA-256 hash, title, author)
- Build settings (voice, speed, engine, loudness profile)
- Per-stage completion records with timestamps and input hashes
- The full chapter list: titles, word counts, detection source, confidence, include flags

Every field the pipeline needs is in `book.json`. Stages communicate through it,
not through environment state or filenames.

**What "resumable" means:** if synthesis stops at chapter 7 chunk 43, re-running
`vorpal build` skips all 42 completed chunks (their WAVs are in the cache under
content-addressed filenames) and resumes from chunk 43. No checkpoint to restore.

## Stages

| # | Stage | Input | Output | Re-runs when |
|---|-------|-------|--------|--------------|
| 1 | **Ingest** | Source file | `book.json` skeleton, raw copy | File hash changes |
| 2 | **Extract** | Source file | `pages.jsonl` | File hash, DPI, `--redo-extract` |
| 3 | **Segment** | `pages.jsonl` | Chapter list in `book.json` | Extract output hash, `--redo-segment` |
| — | **Review gate** | Chapter list | `approved: true` in manifest | When source is `heuristic` or flagged |
| 4 | **Normalize** | Chapter text | `chunks.jsonl` per chapter | Chapter text, voice, speed |
| 5 | **Synthesize** | `chunks.jsonl` | Per-chunk WAVs, per-chapter WAVs | Chunk text + voice + speed cache key |
| 6 | **Master** | Per-chapter WAVs | `.m4b` + `report.md` | Any WAV, metadata, or loudness change |

### Stage 2: Extract

**EPUB** — Parses the OPF spine and NAV/NCX table of contents directly.
Chapter structure is ground truth; no OCR, no geometry.

**Born-digital PDF** — Uses pdfminer/pdfplumber to extract text with block geometry
(x/y coordinates, font size, bold flag). Geometry is preserved in `pages.jsonl`
for the segmenter.

**Scanned PDF** — Rasterises each page, preprocesses (deskew, binarise), runs
Tesseract OCR. Block geometry is recovered from Tesseract's hOCR output.

**Plain text** — Reads UTF-8, splits on blank lines, infers blocks by content.
No geometry.

### Stage 3: Segment

Chapter detection runs a cascade; the first method that produces high-confidence
results wins:

1. **Outline** — embedded TOC (EPUB NCX/nav, PDF bookmarks). Confidence 0.95–1.0.
2. **Printed TOC** — rendered table-of-contents pages. Confidence 0.80–0.95.
3. **Heuristics** — heading-like lines by geometry and pattern. Confidence 0.50–0.85.

Results below the confidence threshold are flagged. The `vorpal review` command
shows flagged chapters; `vorpal review --approve` locks the manifest.

### Stage 4: Normalize

- Expands abbreviations (`Dr.` → `Doctor`, `Vol.` → `Volume`)
- Expands numbers by context (`1917` → `nineteen seventeen` for years)
- Strips running headers, page numbers, footnote markers
- Splits text into TTS-safe chunks respecting a strict hierarchy:
  1. Never across a paragraph break
  2. Only at sentence boundaries within long paragraphs
  3. Never mid-sentence — oversized single sentences are emitted intact

### Stage 5: Synthesize

- Iterates through each chapter's chunks
- Checks the WAV cache: `chunks/<sha256(text+voice+speed)>.wav`
- Cache misses go to the Kokoro TTS engine (GPU preferred)
- Stitches per-chunk WAVs into a per-chapter WAV with 25ms crossfades at chunk
  boundaries and 200ms silence at paragraph breaks

### Stage 6: Master

1. Two-pass EBU R128 loudness normalisation (−18 LUFS, −1.0 dBTP)
2. AAC encode at 128 kbps / 44.1 kHz mono per chapter
3. Concat all chapters via ffmpeg `concat` demuxer
4. Write MP4 chapter atoms (title + start timestamp)
5. Attach cover art and ID3-style metadata
6. Produce `<output>.m4b` and `<output>.mp3` side product

## The chunk cache

The cache key is `sha256(text + voice_id + speed)`. This means:

- **Changing only the title** of a chapter → only mastering re-runs (no synthesis)
- **Changing the voice** → full re-synthesis (all chunk cache keys change)
- **Changing speed** → full re-synthesis
- **Crash mid-synthesis** → resume from last completed chunk on restart
- **Editing `include: false` on a chapter** → only that chapter's synthesis + mastering

## Workdir layout

```
<output>_workdir/
  book.json           the manifest
  pages.jsonl         extracted text with block geometry (PDF only)
  chapter_texts/      per-chapter plain text files
  chunks/             content-addressed WAV cache (one file per TTS chunk)
  chapters/           per-chapter stitched WAV (before mastering)
  chapters_norm/      loudness-normalised per-chapter WAV
  chapters_aac/       encoded per-chapter AAC
  report.md           build summary
```

## Editing the manifest

`book.json` is designed to be hand-edited. Common fields to change:

| Field | Effect |
|-------|--------|
| `chapters[N].title` | Updates chapter marker name — no re-synthesis |
| `chapters[N].include` | Excludes chapter from audio — triggers re-synthesis for that chapter + mastering |
| `chapters[N].spoken_intro` | Synthesised and prepended to the chapter audio |
| `settings.voice` | Changes narrator — full re-synthesis on next build |
| `settings.approved` | Set to `true` to skip the review gate |

After editing, run `vorpal review --approve` then `vorpal build` to apply changes.

## Fidelity guarantee

For EPUB and TXT sources, every byte of body text must make it through
normalisation and into the TTS engine. The `vorpal fidelity` command verifies
this with character-level similarity scoring. A score of 1.000 is the target.
Scores below ~0.995 indicate dropped text and should be investigated.

```bash
vorpal fidelity --source book.epub --workdir book_workdir/
```
