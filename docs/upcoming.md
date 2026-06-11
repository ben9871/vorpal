# What's Coming in vorpal

## Where We Are Now

vorpal is a local, privacy-first tool that converts PDF, EPUB, and plain-text books into M4B audiobooks — the format that Apple Books, Smart AudioBook Player, and most audiobook apps understand natively, complete with chapter markers and cover art.

As of June 2026, 43 phases of development are complete. The full pipeline works end to end: you hand vorpal a file, it extracts and cleans the text, detects chapter boundaries, converts the text to speech using a local neural TTS model (Kokoro, running on your GPU), applies broadcast-standard loudness normalization, and assembles a properly chaptered M4B file. The whole thing runs on your own machine — no cloud, no subscription, no audio leaving your house.

The first real production test was a five-volume set of Leon Trotsky's military writings. The result: `trotsky_v1.m4b`, 19 hours and 16 minutes, 569 MB, built entirely locally. That's the benchmark everything else gets measured against.

The voice suite currently has 11 options: eight single Kokoro voices (American and British, male and female) and three blended voices — weighted combinations of two voices that produce a distinct character without any training. The default is `af_heart`, a warm American female narrator. The deep and steady `blend_deep_steady` (Fenrir + Michael) turned out to be a good fit for the Trotsky material.

There's also a theatrical play mode: vorpal can cast a play — Shakespeare, Beckett, whatever you give it — and assign different voices to different characters automatically. It reads the text, identifies the cast, and routes each character's lines to a different voice.

## The North Star

The goal is simple to state and genuinely hard to execute: *any book, great sound, no friction*. Hand vorpal a PDF you pulled from the Internet Archive or an EPUB from Project Gutenberg, and an hour later you have an audiobook you'd actually want to listen to on a long drive.

"Great sound" means: correct chapter detection, no mispronounced names, no awkward sentence breaks, consistent loudness, a narrator whose voice fits the material. "No friction" means: you shouldn't need to babysit the pipeline or hand-correct a transcript before it will run.

## What's Coming Next

### Tone Detection (Phase 8)

The biggest near-term addition. vorpal will run a fast LLM pass (Claude Haiku) over each paragraph and tag it with a tone — things like `neutral`, `somber`, `tense`, `warm`, `wry`, `urgent`, `reflective`. These tags will feed into TTS engines that support expressive delivery, so the narrator doesn't read a battlefield dispatch in the same flat voice as a letter home.

The important design decision: **the pipeline builds a complete audiobook without this pass**. Tone tags are an enhancement layer, not a requirement. If you don't want to spend tokens on it, or you're running offline, you get a perfectly good audiobook anyway — just without the expressive shading.

Two backends will be supported: a `cli` backend that uses the Claude Code subscription token (no extra cost if you already have a subscription), and an `api` backend for people with an Anthropic API key who want the Batches discount.

### API-Based TTS Engines (Phase 7)

The local Kokoro model is good — fast, free after the initial download, runs offline, produces clean and natural speech. But for people who want the best possible voice quality and are willing to pay for it, vorpal will support cloud TTS engines via the same interface:

- **OpenAI TTS** (gpt-4o-mini-tts): roughly $5–10 per book, good quality, fast
- **Azure Neural TTS**: supports SSML style tags, useful for expressive delivery
- **ElevenLabs v3**: the current leader in voice quality, roughly $50–150 per book for a full-length audiobook

All three use the same `--engine` flag. The local Kokoro engine remains the default and always will — vorpal is not becoming a cloud service.

### Pronunciation Lexicons (Phase 13)

Proper nouns are the Achilles heel of any TTS pipeline. "Trotsky" is fine; "Sverdlov" is a coin flip; specialized technical or historical names are worse. The lexicon feature will let vorpal propose IPA pronunciations for the unusual names it finds in a book, show them to you in a quick review pass, and bake the approved ones into the synthesis. A book is lexicon-tagged once; the file travels with the manifest.

### Dialogue-Aware Delivery (Phase 24)

When a narrator reads quoted speech, it should sound slightly different from straight narration — not a different character voice, just a subtle delivery shift. This phase adds detection of quoted speech and applies a light adjustment to how those passages are synthesized. Same narrator throughout; just more natural.

### Draft Mode (Phase 26)

Full GPU synthesis is fast (about 25 minutes for a 19-hour book on a modern card), but sometimes you just want to check chapter detection or test a voice choice before committing. Draft mode uses Piper, a CPU-fast TTS engine, to produce a rough version quickly — then you switch to the full engine for the final build.

### Library/Batch Mode (Phase 18)

Point vorpal at a folder of EPUBs and walk away. The batch mode processes the whole shelf overnight, producing one M4B per book. This is the mode that makes "converting your Gutenberg collection" practical rather than theoretical.

### In-House Voice Training (Phase 9)

A research spike, not a user-facing feature: train custom Kokoro-compatible voices on properly licensed datasets. The goal is a small suite of voices that are distinctly vorpal's own — not clones of real people. Voice cloning is explicitly out of scope and will never be a feature.

## The Philosophy

A few design commitments that won't change:

**The deterministic core is the product.** Every stage of the pipeline — text extraction, chapter detection, normalization, synthesis, mastering — must produce a complete audiobook without any LLM or cloud call. Optional passes (tone tagging, pronunciation proposals) make the result better, but they're never required. You can run vorpal on an air-gapped machine and get a good audiobook.

**No silent failures.** If body text gets dropped, the pipeline fails loud. If a chapter boundary looks wrong, it flags it for review rather than guessing. The manifest (`book.json`) records every decision; every stage is resumable from where it left off.

**No voice cloning.** The voices in the suite are trained on licensed data or constructed from blends of existing model weights. There is no feature to clone a person's voice, and there won't be.

**Privacy by default.** Your books don't leave your machine unless you explicitly choose a cloud TTS engine. The local pipeline produces professional-quality results without any network calls after the initial model download.
