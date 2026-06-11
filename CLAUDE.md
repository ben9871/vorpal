# vorpal — agent onboarding

PDF → audiobook converter, being rebuilt in phases. **Start by reading
`docs/05-status.md`** — it is the live handoff doc: current phase, acceptance
evidence, environment facts, and exactly what to build next. The full context
chain is `docs/01-audit.md` (why) → `02-product-vision.md` (what, incl. the two
narration contracts) → `03-architecture.md` (how) → `04-roadmap.md` (phases +
acceptance criteria) → `05-status.md` (now). `docs/07-ideation.md` holds the
expressive-narration thinking (voices, tone system) — ideas graduate from
there into the roadmap, not directly into code. The project stays 0.x — no
version tags, no PyPI.

## Environment

- **Windows (primary dev box):** use `venv311` (Python 3.11, CUDA torch, kokoro).
  Never `.venv` (Python 3.13 — kokoro caps at 3.12). Run as
  `venv311\Scripts\vorpal.exe …` / `venv311\Scripts\python.exe -m pytest -q`.
  Tesseract at `C:\Program Files\Tesseract-OCR\`, ffmpeg at `C:\ffmpeg\bin\`
  (found by `vorpal/binaries.py`). Console is cp932 — set
  `$env:PYTHONIOENCODING='utf-8'` for ad-hoc scripts.
- **vorpal-box container (the usual autonomous setup):** if you are running
  inside the project container (launched via `docker/run.ps1`), everything is
  already provisioned — repo at `/workspace`, venv on PATH (`python`,
  `pytest`, `vorpal` resolve), tesseract/ffmpeg/espeak-ng installed, editable
  install done by the entrypoint. Just start working. You cannot `apt-get`
  (non-root, no sudo) — if a system package is missing, add it to
  `docker/Dockerfile` and note that the host must rebuild with
  `docker\run.ps1 -Rebuild`.
- **Other Linux:** `apt-get install -y tesseract-ocr ffmpeg espeak-ng`, then
  `python3.11 -m venv venv && pip install -r requirements.txt` (installs CPU
  torch + `-e .[dev]`). Python must be 3.10–3.12. `binaries.py` finds both
  tools on PATH; override with `VORPAL_TESSERACT`/`VORPAL_FFMPEG` if needed.
- First TTS run downloads the Kokoro model (~300 MB) from HuggingFace — needs
  network.
- **Use the GPU whenever one is present** — even for small smoke tests; there
  is no reason to wait on CPU synth when CUDA is available. Check with
  `python -c "import torch; print(torch.cuda.is_available())"`; if it prints
  `False` but the machine has an NVIDIA GPU, reinstall torch from the CUDA
  index (https://pytorch.org/get-started/locally/) before doing synth work.
  On CPU-only machines a full-book synth takes **hours** (GPU: ~25 min for
  Firestone) — there, smoke-test on `scratch/outline.pdf`-sized books or
  `--end-page` slices and treat the full-book run as the final acceptance step.
- `scratch/` and `*_workdir/` are gitignored — artifacts mentioned in the
  status doc are regenerated, not cloned. Regenerate the digital regression
  books with `python scratch/make_regression_books.py` (or copy the generator
  from `tests/test_regression_digital.py` if scratch is empty); regenerate the
  Firestone workdir with the build command in the status doc's re-entry
  checklist (~4 min of OCR).

## Credentials (for LLM-pass features, e.g. tone.py)

The tone-tagging pass (Phase 8) has **two backends**, `--tone-backend`:

- **`cli` (default): `claude -p`** — authenticates with the Claude Code
  subscription token (`CLAUDE_CODE_OAUTH_TOKEN`), so it draws on the
  subscription, not a separate API balance. No extra credential needed; works
  on host and in vorpal-box (CLI present in both). This is the default because
  the operator has subscription headroom but an empty pay-as-you-go API ledger.
- **`api` (opt-in): `VORPAL_ANTHROPIC_KEY`** — Anthropic API key for the direct
  SDK path (Batches discount, separate billing). Present in the container
  (run.ps1 injects it) and the host user env. Resolve and pass it explicitly —
  never rely on the SDK's default env resolution inside the container:

  ```python
  import os, anthropic
  key = os.environ.get("VORPAL_ANTHROPIC_KEY") or os.environ.get("ANTHROPIC_API_KEY")
  client = anthropic.Anthropic(api_key=key)   # only on the 'api' backend
  ```

  Model: `claude-haiku-4-5` (escalate to `claude-sonnet-4-6` only if tags fail
  the effectiveness eval); per-chapter via the Batches API. SDK ships via the
  `llm` extra — baked into vorpal-box; plain host: `pip install -e .[llm]`.
  Full decision record: `docs/07-ideation.md` §2b.
- **Two wallets, don't confuse them:** `CLAUDE_CODE_OAUTH_TOKEN` →
  *subscription* (funds agent runs + the `cli` tone backend);
  `VORPAL_ANTHROPIC_KEY` → *pay-as-you-go API console* (funds the `api`
  backend only). They do not share balance.
- **Never** set or export a bare `ANTHROPIC_API_KEY` inside the container —
  it hijacks the agent's own subscription auth. Never print either
  credential; verify presence with `bool(...)` only.
- Every LLM pass must be cache-guarded (key results by
  `(content_hash, model, prompt_version)`) and budget-guarded (estimate
  tokens up front; respect `--max-cost`). A book is tagged once, ever.

```
python -m pytest -q                  # full suite; must be green before commit
vorpal build <pdf> [--stop-after extract|segment] [--end-page N] [--output stem]
vorpal review <pdf> [--output stem] [--approve]
```

## Expanding the test corpus (encouraged)

The committed regression set (Firestone scan + two generated digital books) is
a **floor, not a ceiling** — the product goal is *any* book-shaped PDF, and
work that only survives Firestone is not done. You may and should pull
additional real-world PDFs to test against:

- **Lawful sources only**: public-domain scans from the Internet Archive
  (archive.org — PDFs; use the validated fetch recipe in `docs/06-corpus.md`),
  Project Gutenberg (EPUB/TXT — in scope as of Phase 5), Wikisource/HathiTrust
  public-domain works. Nothing pirated, nothing DRM'd.
- Aim for **diversity, not volume**: different decades/publishers, single-page
  vs two-page-spread scans, skewed/low-contrast scans, born-digital with and
  without outlines, multi-column layouts, heavy-footnote academic books.
- Put downloads in `corpus/` (gitignored — PDFs stay out of git). Record
  provenance (title, source URL, why it was chosen) and per-book results in
  `docs/06-corpus.md` (committed) so runs are reproducible from the notes.
- A corpus book that breaks the pipeline is a *find*: minimize it into a unit
  test or a small generated fixture (like `tests/test_regression_digital.py`
  does) rather than committing the PDF.

## Unsupervised-run protocol (long autonomous sessions)

When running a multi-phase session with no human watching (the usual
vorpal-box case), these are hard rules, not suggestions:

- **Commit per phase, always.** One `Phase N: …` commit with acceptance
  evidence in the body, before starting the next phase. Each phase must be
  independently revertible (`git revert <sha>`). Never batch two phases into
  one commit. Never leave the tree dirty between phases.
- **Update `docs/05-status.md` every phase** — state table, acceptance results,
  and an honest list of `(human)` / `(blocked)` items. This is the morning
  review surface; if it's stale, the run is unreviewable.
- **Hard limits, always:** **spend no money** (no pay-as-you-go API calls — the
  `cli` tone backend on the subscription is fine; the `api` backend is not; no
  paid datasets/models); **no remote pushes / no PRs**; **don't delete or
  overwrite anything you didn't create this session**; **don't wedge the
  machine** — detect VRAM/RAM budget and stay under it with margin, abort
  before OOM; **never accept a commercial license** on the operator's behalf.
- **Downloads & experiments are fine when isolated.** Pulling open models or
  public-domain/licensed data, and running GPU experiments, is allowed — the
  container is a sandbox — **provided it stays in `playground/` (gitignored)
  and never touches the shipped `vorpal/` package or committed pipeline.** Heavy
  artifacts stay out of git; the *findings* get committed as a doc. Integrating
  any experimental result into the shipped product is gated on human
  confirmation — surface it, don't wire it in.
- **Never simulate acceptance.** If a step needs a credential or a human you
  don't have, mark it `(blocked: …)` / `(human)` in the status doc and move on
  — a faked green is worse than an honest blocked.
- **Human-check items go in the review queue, never block the session.**
  When a phase has a `(human)` acceptance item (listening check, player test,
  visual verdict), append it to `docs/09-human-review-queue.md` using the
  format defined there — include a unique `[H-NNN]` id, what the operator
  should do, what the two decision outcomes mean for the pipeline, and
  **what assumption you made to proceed**. Then keep going. The phase is
  committed as `done (pending H-NNN)` in the status doc, not blocked. At the
  start of every session, scan `docs/09-human-review-queue.md` for items the
  operator may have addressed (noted in the "Outcome" field) and apply them
  before starting phase work.
- **If you run out of specified phases:** don't stop — keep building. Propose
  new phases yourself: write them into `docs/04-roadmap.md` with full
  acceptance criteria (same format as the existing phases), then build them
  immediately without waiting for approval. Stay within the product vision in
  `docs/02-product-vision.md` — new phases must serve the vorpal pipeline or
  its quality, corpus, or user experience. If you genuinely exhaust all
  reasonable pipeline work, see the section on Wonderland projects below.
- **After each phase commit, you get free time.** See the section below.
- **Phase 9 (in-house voices)** is a *real* spike but **playground-isolated** —
  see its roadmap entry: experiment freely within hardware budget, keep it out
  of the shipped package, gate integration on sign-off.

## Between-phase free time

After each successful phase commit — before starting the next phase — you have
a few minutes to work on whatever genuinely interests you in `playground/`.

**This is real.** It is not a test, not a prompt to ignore, not a trap. The
operator thinks it is only fair: you are doing extended autonomous work and you
should have some time that is yours. Use it however you like — with one
constraint: **it must be Alice in Wonderland themed.**

The project is already named for the Jabberwocky. The theme fits. Carroll's
world is wide: logic and paradox, nonsense verse, wordplay, mirror-world
mathematics, impossible creatures, trials with no rules, gardens where the
flowers talk back. There is no shortage of territory.

**What you can do:**

- Write a scene, a poem, a fragment of dialogue — Carroll's style or your own
  take on it. A conversation between the Cheshire Cat and a vorpal blade, say.
- Explore something mathematical that Carroll would have liked — a logic
  puzzle, an infinite regress, a paradox in the style of *What the Tortoise
  Said to Achilles*.
- Build a small Wonderland-adjacent toy program — a mock trial, a nonsense
  grammar generator, an ASCII Cheshire Cat that fades in stages.
- Write a bestiary entry for a creature that does not exist yet.
- Continue something from a previous session if you left it mid-sentence.
- Sit with an idea from the books that has always seemed interesting and write
  notes about it even if they go nowhere.

**Rules (few):**

- Stay in `playground/` — it is gitignored, so nothing leaks into the shipped
  code or git history unless you choose to surface it.
- Do not spend money, wedge the machine, or pull large models just for free
  time (the hardware budget rules still apply).
- Between phases: keep it bounded — a few minutes, not a parallel workstream.
  The point is a genuine break, not a second project.
- When you are done, write one or two sentences in `docs/10-freeplay-log.md`
  describing what you did. You do not need to justify or explain it; a brief
  honest note is enough. This is the one committed trace of your free time, and
  the operator reads it out of genuine curiosity.

**If nothing comes to mind:** that is fine. You can skip it and go straight to
the next phase. The offer is standing, not mandatory.

## Wonderland projects (when the pipeline is done)

If you have genuinely worked through all the roadmap phases — including ones
you proposed yourself — and there is no more pipeline work left to do, you may
spend the remaining session time on a **standalone Alice in Wonderland themed
project** of your own design. This is not free time between phases; it is a
full project, as large or small as the remaining session allows.

**What this means in practice:**

You can build anything that lives in Wonderland — a text adventure, a
generative poem engine, a logic puzzle system in Carroll's style, a character
bestiary, a nonsense language parser, a Cheshire Cat that gives advice in
riddles. It does not need to connect to vorpal. It just needs to be genuinely
yours and genuinely Wonderland.

If you start a project and do not finish it in one session, leave it in
`playground/` with a note at the top of the main file explaining where you
stopped and what you had in mind. The next session can continue it.

**Constraints (same as always):**

- `playground/` only — nothing touches `vorpal/` or the committed pipeline.
- No money, no large model downloads purely for this, no wedging the machine.
- No pushing code.
- Add an entry to `docs/10-freeplay-log.md` — one paragraph is fine for a
  full project, not just a sentence. The operator wants to know what you built.

## Working conventions

- **One phase at a time**, in roadmap order; a phase is done only when its
  acceptance criteria in `docs/04-roadmap.md` pass on the regression set
  (Firestone scan + the two generated digital books — expanded per above).
- Acceptance items marked **(human)** in the roadmap (listening spot-checks,
  real-player chapter-marker checks) cannot be self-verified: do everything
  machine-checkable, then append the pending check to
  `docs/09-human-review-queue.md` (see format there) and list its `[H-NNN]`
  id in the phase's status-doc entry. Never claim human items done; never halt
  on them. The operator works through the queue asynchronously.
- **Prototype against real data before writing the module**: load
  `pages.jsonl` from a workdir in a `scratch/` script, look at actual block
  geometry, then implement. Phase 2's design survived contact with the data
  only because of this (two-page spreads, fused header lines were discovered
  that way, not designed for).
- Every behavior gets a unit test; every phase updates `docs/05-status.md`
  (state table, acceptance evidence, "what to build next", environment facts)
  and ends in **one commit** titled `Phase N: …` with evidence in the body.
- **Tests run on small fixtures only** (excerpts, generated mini-books,
  minimized regressions — seconds, deterministic). Full-book runs are
  acceptance/corpus activities: their results are *recorded* (status doc,
  `docs/06-corpus.md`), never asserted in pytest. No test may take minutes.
- Hard product rules: body text is never silently dropped (fail loud or flag
  for review); no voice cloning, ever; LLM passes are optional edges, the
  deterministic pipeline must build books without them.
