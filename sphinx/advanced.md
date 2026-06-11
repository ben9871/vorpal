# Advanced Features

> "No, no! The adventures first — explanations take such a dreadful time."
>
> — Lewis Carroll, *Alice's Adventures in Wonderland*

## Draft mode — fast CPU preview

`--draft` switches the TTS engine from Kokoro to Piper, a lightweight CPU-only
model. Synthesis is much faster (near real-time on CPU) but lower quality.
Use it to check chapter structure and narration flow before committing to a
full GPU synthesis run.

```bash
vorpal build book.epub --draft --output book_preview
```

Draft and production builds share the same workdir structure; switching from
draft to full quality on the next build re-synthesises only the draft chunks.

## Loudness profiles

Three profiles target different listening environments:

| Profile | Target LUFS | Notes |
|---------|-------------|-------|
| `headphones` | −18 LUFS | Default. EBU R128. |
| `car` | −16 LUFS | Slightly louder for road noise |
| `speaker` | −20 LUFS | More headroom for room acoustics |

```bash
vorpal build book.epub --profile car
```

## Expressive narration (`--expressive`)

The `--expressive` flag enables a tone-tagging pass that labels each paragraph
with one of: `neutral`, `somber`, `tense`, `warm`, `wry`, `urgent`, `reflective`.

These tags feed into subtle pitch and rate adjustments in the Kokoro engine
layer. The effect is understated by design — the goal is consistency with the
text's register, not dramatic acting.

```bash
vorpal build book.epub --expressive
```

**Backend options** (set with `--tone-backend`):

- `cli` (default) — calls `claude -p` using the Claude Code subscription token.
  No API spend; requires a logged-in Claude Code session.
- `api` — calls the Anthropic API directly using `VORPAL_ANTHROPIC_KEY`.
  Costs money; uses the Batches API for discount pricing.

```bash
vorpal build book.epub --expressive --tone-backend api
```

The tone pass is cached by `(content_hash, model, prompt_version)` — a book is
tagged once and the cache survives rebuilds.

## Pronunciation lexicon (`--lexicon`)

For books with unusual proper nouns, technical terms, or foreign words, the
lexicon pass extracts candidates and proposes phoneme overrides:

```bash
vorpal build book.epub --lexicon
```

The lexicon is stored in the workdir as `lexicon.json`. Edit it to correct any
proposals, then rebuild — the corrected pronunciations are applied at
normalisation time.

## ASR round-trip quality check (`--asr-check`)

After synthesis, runs a Whisper ASR model on a sample of the output audio and
compares the transcript to the source text. Catches systematic mispronunciations
and synthesis artefacts.

```bash
vorpal build book.epub --asr-check

# Use a larger model for more accurate checking
vorpal build book.epub --asr-check --asr-model small

# Sample fraction (default 10%)
vorpal build book.epub --asr-check --asr-fraction 0.25
```

Requires the `audio` extra: `pip install -e ".[audio]"`.

## Footnote narration (`--footnotes`)

By default footnotes are stripped from the narration. The `--footnotes` flag
controls how they are handled:

| Mode | Behaviour |
|------|-----------|
| `none` | Footnotes stripped (default) |
| `inline` | Footnote text inserted immediately after the reference |
| `chapter` | All footnotes collected and spoken at the end of the chapter |

```bash
vorpal build book.pdf --footnotes chapter
```

## Chapter summaries (`--summaries`)

Generates a short summary for each chapter using an LLM and writes them to
`<workdir>/summaries.json`. Summaries are not spoken in the audiobook; they are
a side product for study notes or chapter previews.

```bash
vorpal build book.epub --summaries
```

## OCR repair (`--repair`)

For scanned PDFs, the `--repair` flag runs an LLM pass over low-confidence OCR
blocks to propose corrections before normalisation. Only blocks below
`--repair-threshold` (default 0.70 confidence) are sent to the model.

```bash
vorpal build scan.pdf --repair
vorpal build scan.pdf --repair --repair-threshold 0.80
```

## Export (`vorpal export`)

Export the cleaned, normalised text from a completed build to EPUB or plain text:

```bash
# Export to EPUB
vorpal export book.epub --format epub --output book_clean.epub

# Export to plain text
vorpal export book.epub --format txt --output book_clean.txt
```

The exported text has all boilerplate removed and OCR errors corrected (if
`--repair` was used). This is useful for producing a clean reading edition
alongside the audiobook.

## Library / batch mode (`vorpal library`)

Build all book files in a directory in one command:

```bash
vorpal library --directory my_books/

# With options applied to every build
vorpal library --directory my_books/ --voice blend_deep_steady --draft
```

vorpal discovers all PDF, EPUB, and TXT files in the directory, skips any that
already have a complete workdir, and builds the rest in sequence. A summary
report is printed at the end.

## Web UI (`vorpal serve`)

A thin local web interface for reviewing chapter structure and approving builds:

```bash
vorpal serve book.epub
# opens http://127.0.0.1:7654 in your browser
```

Options: `--host`, `--port`, `--no-browser`

Requires the `web` extra: `pip install -e ".[web]"`.

## Fidelity check (`vorpal fidelity`)

Verify that no body text was silently dropped during normalisation:

```bash
vorpal fidelity --source book.epub --workdir book_workdir/
```

Outputs a per-chapter similarity table and a global score (1.000 = no text
dropped). Only meaningful for EPUB and TXT sources; scanned PDFs have inherent
OCR approximations.
