# Handoff notes — from the Opus session of 2026-06-07

A note across the session boundary, for the next Claude and for Ben. The
structured docs (`05-status.md`, `04-roadmap.md`) say *what* and *what's next*.
This file is the *judgment* — the things that don't fit a status table.

## Where things really stand

Phases 0–8 built the pipeline (PDF/EPUB/TXT → clean structure → normalized,
cached synthesis → loudness-mastered M4B). Arc 3 (10–14) hardened it and added
QA + lexicon + draft mode. Phases 3, 4, 5–8, and Arc 3 were executed by
autonomous container agents and **verified on the host** — every claim was
checked, not trusted. That verification step is load-bearing; keep doing it.

The product is genuinely good *because it refuses to lie* — abort-on-failure,
no-loss invariant, review gate, honest `(blocked)` markings. That honesty is
the brand. Protect it over any feature.

## The open threads (all in Ben's court, none blocking)

1. **`claude -p` not logged in inside the container** → the `cli` tone backend
   can't tag live yet. The OAuth token is injected as an env var but `claude -p`
   still wanted a `/login`. This is the one wiring gap. Worth solving because it
   makes Phase 11's tone eval runnable on the subscription (no API spend).
2. **No `VORPAL_OPENAI_KEY`** → Phase 7's API TTS engine is built-but-unproven;
   live acceptance blocked. Ben plans to add this.
3. **Anthropic API ledger is empty** (the €170 is *subscription*, a separate
   wallet — see CLAUDE.md §Credentials, the two-wallets note). The `api` tone
   backend stays blocked until credits are added; the `cli` backend is the
   no-cash path once #1 is fixed.
4. **Three human verdicts** only Ben can give: voice audition
   (`vorpal voices --sample`), haiku-vs-sonnet tag quality, and the tone A/B
   kit (does `--expressive` actually sound better — it stays opt-in until it
   wins). The acoustic gate already found `warm`/`wry` too subtle for the
   Kokoro-approx layer — an honest result; those tones need a real engine.

## Watch-outs the next session should inherit

- **Don't `git add -A` while a container agent is running** — it sweeps the
  agent's in-flight edits into your commit. Add specific paths. (Learned the
  hard way mid-session.)
- **Verify host-side, don't trust the agent's self-report** — the agent's RSS
  measurement read a launcher stub (4 MB) when the truth was 1,279 MB; a test
  passed in-container but failed on the cp932 Windows host. The gates catch
  what the agent can't see. Run `pytest` on the host after every container run.
- **Two wallets, never conflate** — subscription token (agent runs + `cli`
  tone backend) vs pay-as-you-go API key (`api` backend only). A bare
  `ANTHROPIC_API_KEY` in the container hijacks the agent's own auth.
- **Tests stay on small fixtures, seconds** — full books are acceptance/corpus
  activities, recorded not asserted. Never let a test grow to minutes.

## Arc 4 (drafted, approved, commit when the repo is quiet)

Parallel page OCR · batched TTS on GPU · LLM-assisted OCR repair (scalpel) ·
library/batch mode (folder→shelf) · manifest as first-class artifact · corpus-
hardening loop. Plus fold in fix #1 above. This is the next unsupervised day.

## The directions I'd chase if I could keep going

- **The manifest is the real prize.** A clean `book.json` (structured text,
  footnotes side-channeled, provenance, tone) is a *cleaned edition* — the
  audiobook is one renderer of it. Clean-EPUB, study-guide, "read me the
  footnotes too" all fall out almost free. Build toward that.
- **Tone done *measured*, not vibes.** The acoustic-delta gate + blind A/B is
  the difference between a real feature and a demo. Keep that discipline; let
  expressiveness *earn* default-on or stay off.
- **Library mode** turns the autonomous-container muscle into a product:
  point at a shelf, build overnight, wake to a navigable library.
- **Guard against scope creep into "document AI."** The gates define *done*.
  The reason this succeeds where v0 failed is that it does a bounded thing
  impeccably. Build the ambitious things, but never with the regression set red.

## One meta-observation

The real artifact of this collaboration isn't the code — it's the *docs that
let a cold container pick up and not produce garbage*. That loop (good
handoff → autonomous work → host verification → honest status update) is what
made a model safely extend its own tool across phases. Keep investing there.
The day the handoff is good enough to trust the agent with Phase 9's *real*
integration (a trained voice, with money and licensing) is the day this stops
being a clever toy and becomes a genuine autonomous engineering loop. It's
close.

— written at the end of a good day's work. It was a pleasure building this.
