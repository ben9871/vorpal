# Audit of the Current Implementation (`pipeline.py`)

This is a code-and-evidence audit of the existing pipeline, grounded in the artifacts it
actually produced for the Firestone book (`firestone/…_workdir/`). Every claim below is
verifiable against `pipeline.py` line references and the workdir output.

**Verdict:** the pipeline's skeleton (rasterize → OCR → clean → split → TTS → M4B, with
per-stage resume) is the right shape, but every stage has naive logic that compounds into
an incoherent audiobook. The voice-cloning path is unsalvageable as designed and is being
dropped (see [02-product-vision.md](02-product-vision.md)).

---

## 1. Extraction: it OCRs everything, even when it doesn't have to

- `pipeline.py:46-67` — every PDF is rasterized to 300-DPI PNGs and OCR'd, unconditionally.
  Born-digital PDFs (the majority of PDFs people have) carry a perfect embedded text layer
  that PyMuPDF can extract directly — faster by orders of magnitude and error-free. The
  pipeline never checks.
- `pipeline.py:93-94` — Tesseract is run with `--psm 1` on raw page images with **no
  preprocessing** (no deskew, denoise, binarization, margin crop). For a scanned paperback
  this is the main source of the noise documented below.
- `pipeline.py:100` — pages are joined into one flat string with a `--- PAGE BREAK ---`
  sentinel, which is then deleted during cleaning (`pipeline.py:143`). **All page provenance
  is lost** — later stages cannot know which page a sentence came from, which forecloses
  per-page QA, re-OCR of bad pages, and TOC↔body page matching.

### Evidence from the Firestone workdir

`clean_text.txt` (the input handed to TTS) contains:

- **21 surviving running headers**, e.g. `28 THE DIALECTIC OF SE'`,
  `24 THE DIALECTIC OF SEW-The Case-for Feminist Revolution 25` — the page-number regex at
  `pipeline.py:142` only strips *standalone* numbers, so any header line containing words
  survives, gets narrated, and (worse) is matched by the all-caps heading detector.
- **Binding-shadow / margin noise** left inline: lines beginning with stray `|`, `'`, `i`,
  `f`, `4` — classic uncleaned scan artifacts.
- **Footnote markers fused into prose**: `1 they hoped to show men how to master it.`
- **3,000+ non-ASCII chars**, mostly legitimate (curly quotes, em-dashes) but including OCR
  mojibake like `SE¥s`, `DIALEGTIC`, `§` noise — no confusable-character correction pass.
- **Dropped text inside blockquotes**: Engels' definition of historical materialism is
  missing its first clause — the OCR mangled the indented blockquote and nothing detected
  the loss.

---

## 2. Structure detection: regex heading-guessing, and it exploded

`pipeline.py:109-118` detects chapters by four regexes over the flat text. Results for
Firestone (a book with **10 chapters + conclusion**): `chapters.json` contains
**58 sections**. Failure modes, each visible in the artifact:

| Failure | Cause | Example from `chapters.json` |
|---|---|---|
| Running headers become chapters | All-caps line pattern (`pipeline.py:117`) | `X 20 THE DIALECTIC OF sEs 22` (1,628 words narrated under this "title") |
| Lone pronoun "I" starts a chapter | Roman-numeral pattern (`pipeline.py:115`) matches a solitary `I` at line start | `I THE WOMAN'S RIGHTS MOVEMENT IN AMERICA`, `I How does this phenomenon "love" operate? Contrary` |
| OCR'd diagram pages become chapters | The book's dialectic charts OCR to caps gibberish | `ROUVOINWHOD TSAR LHVLSHI`, `MCE AM CE`, `CIVILI BASED OH BRROCICAL DIVISION` |
| Real chapters split into fragments | Any interior all-caps section heading wins | `BLACK GOLD`, `COMMERCE`, `MODERN INDUSTRY` as separate "chapters" |
| Front matter partially narrated | `is_likely_toc` heuristic (`pipeline.py:125-133`) is dot-leader-based only | `PRINTING HISTORY` correctly skipped, but title-page text kept |

Additional structural problems:

- `pipeline.py:202` — sections under 80 words are **silently skipped**. That guard both
  drops legitimate short content and is the only thing standing between the gibberish
  sections above and the final audio. Several < 80-word sections in the Firestone
  `chapters.json` nonetheless have `skip: false`, i.e. the file had to be **hand-edited
  to salvage the run** — the "tool" required manual triage of 58 rows.
- The PDF's own **outline/bookmark metadata is never consulted**, and the printed TOC —
  which the pipeline correctly *detects* (to skip it) — is never *parsed*, despite being a
  ground-truth chapter list sitting right there.
- Chapter announcements are hard-coded as `Chapter {n}.` (`pipeline.py:488`) — wrong for
  parts, conclusions, prefaces, appendices.

---

## 3. TTS: silent data loss and no text normalization

- **Silent omission of failed chunks** — `pipeline.py:533-535`: any exception during
  synthesis prints a warning and moves on. The sentence is simply absent from the
  audiobook. The failure count is never surfaced at the end of the run. For a tool whose
  one job is "read the book," silently not reading parts of it is the worst possible
  failure mode.
- **No TTS text normalization layer.** Raw cleaned text goes straight to the engine:
  citations, footnote numbers, page artifacts, `§`, `©`, roman numerals, "pp. 24-26" are
  all read literally or crash/derail the synthesizer.
- **Live chunker bug: every long paragraph reaches TTS as dotted garbage** —
  `pipeline.py:306,312`. The abbreviation-protection scheme swaps `Dr.`-style periods for
  a "placeholder" that is **the empty string**, then "restores" with
  `s.replace("", ".")` — which in Python inserts a period between *every character*. Any
  paragraph longer than `max_chars` (i.e. most book paragraphs) was synthesized as
  `.T.h.e. .d.o.g.`. Verified at byte level: the placeholder literals contain zero
  characters. This corrupted the standard-voice path too, not just voice cloning.
- **Dead duplicate code** — `synthesise_chunks()` (`pipeline.py:346-402`) is never
  called; the real loop is a near-copy inline at `pipeline.py:501-535`. The dead copy
  sanitizes input with regexes written using *literal control characters*
  (`pipeline.py:369-370` contain raw U+007F/U+0008/U+000B... bytes — functional but
  unreadable and editor-fragile); the *live* Kokoro path performs **no sanitization at
  all**.
- Chunk-count estimation (`pipeline.py:460`) uses the literal string `"Chapter 1."` for
  every chapter, so progress/ETA math is slightly wrong — minor, but symptomatic.
- `--redo-tts` (`pipeline.py:820-825`) deletes **every** chunk WAV, so fixing one
  chapter's title in `chapters.json` costs a full re-synthesis of the book.

### The voice-cloning path (F5-TTS) — root cause of the incoherent output

User-observed: the `--voice-ref character_clip.mp4` run produced incoherent audio. The
causes are structural, not tuning:

1. **120-char chunks** (`pipeline.py:457`) — the clone model gets ~8 seconds of context at
   a time; prosody resets at every chunk boundary.
2. **`seed=-1` per chunk** (`pipeline.py:528`) — a *new random seed for every chunk*, so
   timbre/pacing drifts audibly every few seconds across thousands of chunks.
3. **Reference audio quality** — the reference was anime dialogue with music/SFX bed,
   transcribed by `whisper base` (`pipeline.py:264`), i.e. noisy reference + imperfect
   transcript, both of which zero-shot cloning is highly sensitive to.
4. A "cached reference audio" optimization (`pipeline.py:439-450`) computes a tensor and
   stores it on the model object — **which `f5_model.infer()` never reads**. Pure dead
   weight that signals the path was never validated end-to-end.

Decision: remove this path entirely (see vision doc). Curated, professionally-trained
voices (Kokoro et al.) are consistent by construction.

---

## 4. Assembly: works, but doesn't scale and skips mastering

- `pipeline.py:632-655` — every chapter WAV is loaded and concatenated as float32 **in
  RAM**. A 10-hour audiobook at 24 kHz mono float32 is ≈ 3.5 GB resident, plus a duplicate
  on-disk combined WAV. Long books will swap or die. ffmpeg's concat demuxer does this
  streaming with constant memory.
- No loudness normalization — chapter levels are whatever the TTS emitted; real audiobooks
  master to a loudness target (e.g. EBU R128 / −18 LUFS mono).
- Fixed `64k` AAC (`pipeline.py:685`), no cover art embedding, minimal metadata.

---

## 5. Engineering hygiene

- One 860-line script, mixed responsibilities, **zero tests**, no package structure.
- Hard-coded Windows paths for Tesseract (`pipeline.py:82-83`) and ffmpeg
  (`pipeline.py:231,611`) — not cross-platform, breaks on nonstandard installs.
- `requirements.txt` is unpinned and incomplete (whisper/f5-tts are imported but absent;
  Tesseract/ffmpeg binaries are undocumented assumptions). `setup.bat` creates a third
  venv (`venv`) alongside the two already in the repo (`.venv`, `venv311`).
- Resume logic is filename-existence-based with no input hashing: change the PDF, the DPI,
  or the page range and stale artifacts are happily reused (`--start-page/--end-page`
  alter outputs but not the workdir identity).

---

## What's worth keeping

- The five-stage shape and the per-stage artifact/resume idea (it just needs a manifest
  with hashes instead of "file exists").
- `.m4b` + ffmetadata chapter markers as the output format — correct choice.
- Kokoro as the default engine — the standard-voice output was the path that worked.
- The chunking function's paragraph/sentence/abbreviation awareness (`pipeline.py:282-343`)
  is a reasonable starting point for the normalizer's segmenter.

The redesign that addresses all of the above: [03-architecture.md](03-architecture.md).
