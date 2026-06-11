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

---

## Update — 2026-06-08: Arc 4 credential gap & manual-seeding protocol

Added by Ben after reviewing the Arc 4 queue. This note explains a deliberate
short-term compromise so future agents don't misread it as a gap to work around.

### The situation

`VORPAL_ANTHROPIC_KEY` has zero API credits. `claude -p` inside the container
needs an interactive `/login` that an autonomous agent cannot complete. This
blocks **live LLM calls** for Phase 17 (OCR repair) and Phase 29 (chapter
summaries). It does *not* block Phases 15–16 (parallelism) or 18–20 (library,
export, corpus) — those phases have no LLM dependency.

### The approach: manual seeding

For any LLM-backend phase in Arc 4 (and later arcs where credentials are still
absent), the agent should:

1. Take real data as input — actual low-confidence OCR blocks from the Firestone
   `pages.jsonl`, not synthetic examples.
2. Write a plausible proposal by hand — the same JSON structure and field names
   the LLM would return. Correctness of the proposal content is secondary; what
   matters is that the shape is right so downstream code exercises all its paths.
3. Inject the proposal into the manifest at the point where the LLM call would
   have written it.
4. Run the full downstream workflow: review surface, approve/reject round-trip,
   apply path in normalization. All of that code runs against real data.
5. In the phase's acceptance evidence in the status doc, write clearly:
   *"LLM proposal step manually seeded — workflow and code paths verified; live
   call blocked on credentials."*

### Why this is sound (not a shortcut)

The value of Phase 17 is not "the LLM produces good repairs." That can't be
verified without live calls anyway, and it's Ben's job to evaluate the quality
of proposals once the token is live. The value is: **the pipeline correctly
accepts a proposal, surfaces a diff, lets the user approve/reject, and applies
approved entries before TTS — without touching the deterministic path when the
flag is absent.** All of that is code logic, not LLM output, and manual seeding
verifies it completely.

This is the same pattern used successfully in Phase 8 (tone cache pre-populated
manually to verify the cache-hit path) and Phase 13 (lexicon round-trip tested
without a live proposal call). Both of those were later confirmed correct when
real data flowed through.

### What changes when credentials arrive

Nothing architectural. The agent or Ben adds the token, runs the live path, and
the output from the LLM slots into the same manifest fields the manual seed used.
The review→approve→apply flow is already proven. The only new thing to verify is
proposal *quality* — which is a human judgment call.

### The `claude -p` `/login` situation

The container has `CLAUDE_CODE_OAUTH_TOKEN` injected but `claude -p` still
demanded `/login` when tested. This is almost certainly a one-time interactive
setup step that can't be automated. Mark it `(human: claude -p needs /login in
an interactive session)` in the status doc and do not retry in an unattended
run. Once Ben logs in once from inside the container, the token should persist
in the Claude config volume (`claude-config`) and subsequent container runs will
find it already authenticated.
