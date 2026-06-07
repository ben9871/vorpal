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
- **Do NOT, while unsupervised:** spend money (no pay-as-you-go API calls — the
  `cli` tone backend on the subscription is fine; the `api` backend is not);
  download model weights or datasets > 100 MB *unless the current phase
  explicitly names that download* (Whisper `base` in Phase 12, etc.); push to
  any remote / open PRs; delete or overwrite anything you didn't create this
  session; accept a license or make a legal/financial commitment on the
  operator's behalf; run a single job expected to exceed ~1 hour without it
  being the phase's stated deliverable.
- **Never simulate acceptance.** If a step needs a credential, a download, or a
  human you don't have, mark it `(blocked: …)` or `(human)` in the status doc
  and move on — a faked green is worse than an honest blocked.
- **If you run out of specified work:** do not invent risky tasks. Write a
  concrete proposal for the next phase into the roadmap, update the status doc,
  and stop cleanly. A clean stop with a good handoff is a successful run.
- **Phase 9 (in-house voices) is proposal-only** — see its roadmap entry. No
  training, no downloads, no spend under any circumstances while unsupervised.

## Working conventions

- **One phase at a time**, in roadmap order; a phase is done only when its
  acceptance criteria in `docs/04-roadmap.md` pass on the regression set
  (Firestone scan + the two generated digital books — expanded per above).
- Acceptance items marked **(human)** in the roadmap (listening spot-checks,
  real-player chapter-marker checks) cannot be self-verified: do everything
  machine-checkable, then list the pending human checks explicitly in
  `docs/05-status.md` — never claim them done.
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
