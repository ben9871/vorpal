# CLI Reference

> "Would you tell me, please, which way I ought to go from here?"
> "That depends a good deal on where you want to get to," said the Cat.
>
> — Lewis Carroll, *Alice's Adventures in Wonderland*

All commands are invoked as `vorpal <command> [options]`.

---

## `vorpal build`

Run the full pipeline from source file to `.m4b` audiobook.

```
vorpal build INPUT [options]
```

**Input/output:**

| Flag | Default | Description |
|------|---------|-------------|
| `INPUT` | required | PDF, EPUB, or TXT file |
| `--output STEM` | input filename | Output stem (produces `<STEM>.m4b`) |
| `--start-page N` | 0 | Skip to page N, 0-indexed (PDF only) |
| `--end-page N` | — | Stop at page N exclusive (PDF only) |
| `--dpi N` | 300 | OCR rasterisation DPI (PDF only) |

**Metadata:**

| Flag | Description |
|------|-------------|
| `--title TEXT` | Audiobook title (overrides source metadata) |
| `--author TEXT` | Author name |
| `--year TEXT` | Publication year |
| `--language TEXT` | Language code (e.g. `en`) |
| `--publisher TEXT` | Publisher name |
| `--cover PATH` | Cover image file |

**Voice and speed:**

| Flag | Default | Description |
|------|---------|-------------|
| `--voice ID` | `af_heart` | Voice from registry (see `vorpal voices`) |
| `--speed N` | 1.0 | Narration speed multiplier |

**Pipeline control:**

| Flag | Description |
|------|-------------|
| `--stop-after extract\|segment` | Stop after the named stage for inspection |
| `--redo-extract` | Re-run OCR/extraction even if cached |
| `--redo-segment` | Re-run chapter detection even if cached |
| `--redo-tts` | Delete existing WAVs and re-synthesise |
| `--keep-temp` | Do not delete intermediate WAV files after mastering |
| `--allow-gaps` | Insert audible beep markers for failed chunks (default: abort) |
| `--crossfade-ms N` | 25 | Crossfade duration between chunks (ms) |
| `--max-cost N` | — | Abort if estimated LLM cost exceeds N USD |

**Optional features:**

| Flag | Description |
|------|-------------|
| `--draft` | Use Piper (CPU fast) instead of Kokoro |
| `--profile headphones\|car\|speaker` | Loudness profile (default: `headphones`) |
| `--expressive` | Enable tone-tagging pass (`--expressive` narration) |
| `--tone-backend cli\|api` | Tone tagging backend (default: `cli`) |
| `--tone-model haiku\|sonnet` | LLM model for tone tagging (default: `haiku`) |
| `--lexicon` | Run pronunciation lexicon extraction pass |
| `--lexicon-backend cli\|api` | Lexicon backend |
| `--asr-check` | Run Whisper ASR round-trip quality check |
| `--asr-model tiny\|base\|small` | Whisper model size (default: `tiny`) |
| `--asr-fraction N` | 0.10 | Fraction of audio to check (0.0–1.0) |
| `--repair` | Run LLM OCR repair pass on low-confidence blocks |
| `--repair-backend cli\|api` | Repair backend |
| `--repair-threshold N` | 0.70 | OCR confidence threshold for repair |
| `--summaries` | Generate per-chapter LLM summaries |
| `--summaries-backend cli\|api` | Summaries backend |
| `--footnotes none\|inline\|chapter` | Footnote narration mode (default: `none`) |

---

## `vorpal review`

Inspect chapter detection results; edit `book.json`; approve for synthesis.

```
vorpal review INPUT [options]
```

| Flag | Description |
|------|-------------|
| `--output STEM` | Workdir stem (default: input filename) |
| `--approve` | Set `approved: true` in manifest and unlock synthesis |
| `--tones` | Show tone labels (if `--expressive` was run) |
| `--lexicon` | Show lexicon proposals |
| `--repairs` | Show OCR repair proposals |

---

## `vorpal voices`

List and audition narrator voices.

```
vorpal voices [options]
```

| Flag | Description |
|------|-------------|
| `--sample` | Synthesise an audition WAV for every voice → `voice_samples/` |
| `--text TEXT` | Custom audition text for `--sample` |

---

## `vorpal export`

Export cleaned text from a completed build.

```
vorpal export INPUT --format epub|txt [options]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--format epub\|txt` | required | Output format |
| `--output PATH` | — | Output file path |
| `--workdir-output` | off | Write output to the workdir |

---

## `vorpal library`

Batch-build all book files in a directory.

```
vorpal library --directory DIR [options]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--directory DIR` | required | Directory containing PDF/EPUB/TXT files |
| `--voice ID` | `af_heart` | Voice applied to all builds |
| `--speed N` | 1.0 | Speed applied to all builds |
| `--dpi N` | 300 | OCR DPI (PDF only) |
| `--stop-after extract\|segment` | — | Stop after stage for all files |
| `--draft` | off | Use Piper draft engine |

---

## `vorpal serve`

Launch the local web UI for reviewing and approving builds.

```
vorpal serve INPUT [options]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--output STEM` | input filename | Workdir stem |
| `--host HOST` | `127.0.0.1` | Bind host |
| `--port N` | 7654 | Port |
| `--no-browser` | off | Do not open the browser automatically |

Requires `pip install -e ".[web]"`.

---

## `vorpal fidelity`

Compare normalised text against source to verify no body text was dropped.

```
vorpal fidelity --source FILE --workdir DIR [options]
```

| Flag | Description |
|------|-------------|
| `--source FILE` | Original source EPUB or TXT |
| `--workdir DIR` | Build workdir |
| `--output PATH` | Write report to file (default: stdout) |

---

## `vorpal fetch-play`

Download a plain-text play from Project Gutenberg.

```
vorpal fetch-play --title-or-id TITLE_OR_ID [options]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--title-or-id TEXT` | required | Gutenberg title (fuzzy) or numeric ID |
| `--corpus-dir DIR` | `corpus/plays` | Destination directory |

---

## `vorpal cast`

Print the automatic voice cast for a play file.

```
vorpal cast INPUT [options]
```

| Flag | Description |
|------|-------------|
| `--cast-override JSON_OR_STRING` | Override specific character assignments |
| `--narrator VOICE` | Narrator/stage-directions voice (default: `bm_george`) |
| `--best-voice VOICE` | Force all characters to one voice |

---

## `vorpal play`

Build a multi-voice audiobook from a stage play.

```
vorpal play INPUT [options]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--chapters act\|scene` | `act` | Chapter boundary level |
| `--stage-directions skip\|narrator` | `skip` | Stage direction handling |
| `--cast-override JSON_OR_STRING` | — | Override character voice assignments |
| `--voice ID` | `bm_george` | Default narrator voice |
| `--best-voice ID` | — | Force all voices to a single voice |
| `--output STEM` | input filename | Output stem |
| `--draft` | off | Use Piper draft engine |
| `--profile headphones\|car\|speaker` | `headphones` | Loudness profile |
| `--approve` | off | Auto-approve chapter detection |
| `--no-tone-hints` | off | Disable emotion hints from stage direction context |

---

## `vorpal cast-audition`

Synthesise a short audition WAV for each character.

```
vorpal cast-audition INPUT [options]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--output DIR` | `cast_audition/` | Output directory |
| `--cast-override JSON_OR_STRING` | — | Override character assignments |
