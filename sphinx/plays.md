# Theatrical Plays

vorpal has a dedicated mode for stage plays (`vorpal play`) that assigns a
distinct narrator voice to each character. Feed it *Hamlet* or *Waiting for
Godot* and each character speaks in their own voice.

## How it works

1. **Parse** — the play text is parsed into beats: dialogue lines tagged with
   speaker, stage directions, act/scene boundaries
2. **Character extraction** — all speaking characters are identified and
   classified by role type and gender
3. **Voice casting** — the casting algorithm assigns a voice from the registry
   to each character, considering gender match and role weight
4. **Synthesis routing** — each chunk is synthesised with its assigned voice
5. **Assembly** — chapters follow act or scene boundaries; stage directions are
   spoken by the narrator voice or skipped

## Fetching a play

vorpal can download plain-text plays from Project Gutenberg:

```bash
vorpal fetch-play --title-or-id "hamlet"
# or by Gutenberg ID:
vorpal fetch-play --title-or-id 1787
```

Downloaded plays go to `corpus/plays/` by default. Use `--corpus-dir` to
change the destination.

## Viewing the cast sheet

Before building, inspect the automatic voice assignment:

```bash
vorpal cast hamlet.txt
```

Output example:

```
HAMLET          am_fenrir     (male lead, deep commanding)
HORATIO         am_echo       (male secondary)
GHOST           am_michael    (male secondary)
OPHELIA         af_heart      (female lead, warm expressive)
GERTRUDE        bf_emma       (female secondary, British)
POLONIUS        bm_george     (male elder, British)
[narrator]      bm_george     (stage directions / default narrator)
```

## Overriding the cast

Pass a JSON file or a comma-separated string to `--cast-override`:

```bash
# Override two characters
vorpal play hamlet.txt --cast-override "HAMLET=am_michael,OPHELIA=af_sky"
```

Or write a JSON file:

```json
{
  "HAMLET": "blend_deep_steady",
  "OPHELIA": "af_nova"
}
```

```bash
vorpal play hamlet.txt --cast-override cast.json
```

## Building the audiobook

```bash
# Full build with act-level chapters (default)
vorpal play hamlet.txt --output hamlet

# Scene-level chapters (finer navigation)
vorpal play hamlet.txt --chapters scene --output hamlet_scenes

# Speak stage directions with the narrator voice
vorpal play hamlet.txt --stage-directions narrator

# Skip stage directions entirely (default)
vorpal play hamlet.txt --stage-directions skip
```

## Auditioning the cast

Generate a short WAV per character to verify the casting before a full build:

```bash
vorpal cast-audition hamlet.txt --output hamlet_audition/
```

Each file is named `<CHARACTER>_<voice_id>.wav`.

## Options reference

| Flag | Default | Description |
|------|---------|-------------|
| `--chapters` | `act` | Chapter boundaries: `act` or `scene` |
| `--stage-directions` | `skip` | What to do with stage directions: `skip` or `narrator` |
| `--cast-override` | — | JSON file or `KEY=val,KEY=val` string |
| `--voice` | `bm_george` | Default narrator / stage-direction voice |
| `--best-voice` | — | Force all characters to a single voice (disables casting) |
| `--no-tone-hints` | off | Disable emotion hints from stage direction context |
| `--draft` | off | Use Piper (CPU, fast) instead of Kokoro |
| `--profile` | `headphones` | Loudness profile |
| `--approve` | off | Auto-approve chapter detection |

## Supported formats

The play parser handles **Project Gutenberg plain-text** format:
act/scene headings, `CHARACTER. Dialogue text.` attribution, stage directions
in brackets or italics, and running headers in the Gutenberg style.

Shakespeare, Beckett, and most Gutenberg dramatic texts work without
modification. Non-standard layouts may need preprocessing.

## Example — Hamlet end to end

```bash
vorpal fetch-play --title-or-id 1787          # download Hamlet
vorpal cast corpus/plays/hamlet.txt           # inspect cast
vorpal cast-audition corpus/plays/hamlet.txt  # optional audition clips
vorpal play corpus/plays/hamlet.txt \
    --chapters act \
    --stage-directions narrator \
    --output hamlet
```

Output: `hamlet.m4b` with one chapter per act, each character in their own voice.
