# Human Review Queue

The agent appends to this file whenever it surfaces an item that needs a human
decision. **Nothing in the pipeline blocks on this queue** — for every item the
agent states what it assumed in order to keep going. Work through it when you
have time; cross off items by updating the status to `✅ done` and noting the
decision.

**Agent instruction (read at the start of every session):** Scan this file
before starting work. If any open item was addressed by the operator (an audio
file was listened to, a credential was added, a flag was set), update its entry
to `✅ done`, note the outcome, and apply it to the relevant code or manifest.
Then proceed with the session's phase work.

**Format for new entries:**

```
### [H-NNN] Phase N — Short title
**Added:** YYYY-MM-DD  **Status:** open
**What to review / do:** concrete action (file path, command, decision)
**Decision options:** what "yes" and "no" mean for the pipeline
**Agent's assumption:** what the agent did / did not do in order to proceed
**Outcome (fill in when done):** …
```

---

## Open items

### [H-001] Phase 9 — Voice listening verdict
**Added:** 2026-06-07  **Status:** open

**What to review / do:**
Play these two files back to back:
- `playground/final_vorpal_narrator_v1.wav` — the designed PCA voice
- `playground/final_bm_george_baseline.wav` — current default narrator

Answer: is the designed voice (a) distinctly different from bm_george,
(b) natural-sounding, (c) better suited to non-fiction narration?

**Decision options:**
- **Yes → approve:** name the voice (suggested: `am_rector` or `am_scholar`)
  and confirm registry integration. The entry template is in
  `docs/08-voice-training-spike.md` §8 — the agent will add it to
  `vorpal/tts/voices.py` and move the `.pt` file to the committed voice store.
- **No → reject:** existing `bm_george` + `bm_daniel` blend already covers
  the clear-male-narrator use case. No action needed.

**Agent's assumption:** Voice not yet wired into the registry. The `.pt` file
sits in `playground/` (gitignored) and is not referenced by any shipped code.

**Outcome (fill in when done):** …

---

### [H-002] Phase 7 / Phase 21 — OpenAI TTS live acceptance
**Added:** 2026-06-07  **Status:** open

**What to review / do:**
Provision `VORPAL_OPENAI_KEY` in the Windows user environment (and inject it
into the container via `docker/run.ps1`). Once set, the agent can complete
Phase 21 (1-chapter Firestone build, cost estimate, network-abort test, manual-
tone acoustic delta) without any other changes.

**Decision options:**
- **Add key:** agent completes Phase 21 in the next session; marks live
  acceptance items done; APIEngine path is fully proven.
- **Defer:** Phase 21 stays `(blocked: VORPAL_OPENAI_KEY not set)`; the
  Kokoro-approximation path remains the only proven realization layer.

**Agent's assumption:** `APIEngine` is built, unit-tested against the mock
engine, and wired into the CLI. It is not run live. Phase 7 acceptance is
marked `done (pending live)`.

**Outcome (fill in when done):** …

---

### [H-003] Phase 8 / Phase 11 / Phase 22 — Blind A/B tone verdict
**Added:** 2026-06-07  **Status:** open

**What to review / do:**
Listen to the paired clips and pick which version reads better (no peeking at
which is which until after):

Phase 11 demo kit (Kokoro approximation, somber tone):
- `scratch/ab_kit_demo/neutral_firestone_ch1_neutral_vs_somber.wav`
- `scratch/ab_kit_demo/expressive_firestone_ch1_neutral_vs_somber.wav`

(Phase 22 clips to be added here once generated against the instruction engine.)

**Decision options:**
- **Expressive wins:** `--expressive` can be promoted from opt-in toward a
  recommended default. The agent will update the CLI help text and README.
- **Expressive doesn't win (or can't tell):** `--expressive` stays opt-in,
  clearly documented as experimental. No code change needed.
- **Partial:** some tones work, some don't — the agent can narrow
  `supported_tones` on the Kokoro approximation engine to only the ones that
  pass both the acoustic gate and your ear.

**Agent's assumption:** `--expressive` is opt-in, off by default. The acoustic
gate (Phase 11) found 5/7 tones pass on the Kokoro layer; `warm` and `wry` are
flagged as below threshold and documented in the status doc.

**Outcome (fill in when done):** …

---

### [H-004] Phase 11 — Live tone tagging (credentials)
**Added:** 2026-06-07  **Status:** open

**What to review / do:**
Either:
- Add API credits to the `VORPAL_ANTHROPIC_KEY` account, **or**
- Run `claude /login` once in an interactive container session so the
  OAuth token persists in the `claude-config` Docker volume.

Once either is done the agent can run `vorpal build firestone.pdf --expressive`
and verify: neutral fraction ≳ 60%, tagging twice is a cache hit, histogram
in `report.md`.

**Decision options:**
- **Add credits / login:** agent completes Phase 11 live acceptance in the
  next session.
- **Defer:** Phase 11 stays `done (pending live)`. The tagger code and cache
  logic are verified via manual pre-population; quality of LLM tags is
  unknown.

**Agent's assumption:** Tagger code is complete and cache-correct. Live tag run
has not been performed.

**Outcome (fill in when done):** …

---

### [H-005] Phase 3 — Listening spot-check (narration quality)
**Added:** 2026-06-07  **Status:** open

**What to review / do:**
On a GPU machine, run a full Firestone build and listen to 3 random 2-minute
segments. Check: (a) no narrated junk (headers, page numbers, footnote markers),
(b) no mid-sentence prosody breaks at chunk boundaries.

**Decision options:**
- **Passes:** Phase 3 is fully accepted. Note the build date and confirm in
  the status doc.
- **Fails:** file an issue with the exact text / timestamp of the problem so
  it can be minimized into a test.

**Agent's assumption:** All machine-checkable Phase 3 criteria pass (normalization
suite, `failed: 0` on synth, selective re-synth on title edit). The listening
check is the only unverified item.

**Outcome (fill in when done):** …

---

### [H-006] Phase 4 — Chapter marker verification in a real player
**Added:** 2026-06-07  **Status:** open

**What to review / do:**
Open a full Firestone `.m4b` in VLC or BookPlayer. Tap through the chapter
markers and confirm they land at the correct chapter starts (not mid-sentence,
not on silence).

**Decision options:**
- **Passes:** Phase 4 fully accepted.
- **Fails:** note which chapter(s) are off and by how much — the mastering
  stage's marker-offset logic can be debugged from that data.

**Agent's assumption:** Marker timestamps are verified programmatically
(duration sum vs chapter audio lengths). The real-player check is the only
unverified item.

**Outcome (fill in when done):** …

---

### [H-007] Phase 6 — Voice audition (pick favourites)
**Added:** 2026-06-07  **Status:** open

**What to review / do:**
Run `vorpal voices --sample` on a GPU machine. It renders one clip per voice
into `voices_preview/`. Listen to all 11 (8 singles + 3 blends) and note
which you prefer for different book types (literary, academic, conversational).

**Decision options:**
- **Anything goes:** no code change; the registry stays as-is.
- **Remove a voice:** the agent can drop it from the registry.
- **Adjust a blend recipe:** give a new weight (e.g. "Heart 70%, Nova 30%
  instead of 65/35") and the agent will update the registry and invalidate
  affected cache entries.

**Agent's assumption:** All 11 voices are in the registry with the recipes
from Phase 6. No audition has been run.

**Outcome (fill in when done):** …

---

### [H-008] Phase 24 — Dialogue delivery spot-check
**Added:** 2026-06-08  **Status:** open  *(pending Phase 24)*

**What to review / do:**
After Phase 24 lands: run a build on a chapter with substantial quoted speech
(Pride and Prejudice is the obvious choice — `corpus/pride_and_prejudice_pg1342.epub`).
Listen to the dialogue sections and confirm the delivery shift sounds natural,
not theatrical.

**Decision options:**
- **Natural:** keep `dialogue_style` enabled in the registry for voices that
  support it.
- **Too theatrical / jarring:** reduce the shift magnitude, or disable
  `dialogue_style` by default and gate it behind `--dialogue`.
- **Undetectable:** shift is too subtle — increase it or document that the
  Kokoro-approx layer can't realize it reliably (same honest finding as
  `warm`/`wry` in Phase 11).

**Agent's assumption:** Phase 24 not yet built. This item is pre-registered so
the agent adds its result here rather than creating a new entry.

**Outcome (fill in when done):** …

---

### [H-009] Phase 23 — StyleTTS2 voice verdict
**Added:** 2026-06-08  **Status:** open

**What to review / do:**
Phase 23 is done. Listen to:
- `playground/s2_default_a0.3_b0.7.wav` — StyleTTS2 default style (LJSpeech ref)
- `playground/s2_textdriven_a0.9_b0.9.wav` — StyleTTS2 text-driven style
- `playground/final_vorpal_narrator_v1.wav` — Phase 9 Kokoro PCA voice (male)
- `playground/final_bm_george_baseline.wav` — bm_george baseline (male)

**Important context:** The StyleTTS2 samples use a female reference voice (LJSpeech
public domain). They sound female-pitched (~190 Hz). The Kokoro voices are male
(~140-152 Hz). A proper male-voice StyleTTS2 sample would require obtaining a
short LibriVox male speaker clip. The current samples demonstrate StyleTTS2
*capability*, not a directly comparable male narrator character.

**Decision options:**
- **StyleTTS2 quality is clearly better, proceed with male reference:**
  Agent will download a short LibriSpeech test-clean male speaker clip (public
  domain), extract the style, and synthesize a male narrator comparison sample.
  This unlocks a proper three-way comparison.
- **Kokoro PCA voice is still the better path:**
  If H-001 was approved (Kokoro PCA voice), proceed with that. StyleTTS2
  stays in `playground/` as a researched option.
- **Neither approach is compelling:**
  Keep the existing registry voices (`bm_george`, `bm_daniel` blend).

**Agent's assumption:** StyleTTS2 model is installed and working (34% VRAM peak,
0.72 GB idle). All synthesis code is in `playground/styletts2_spike.py`.
Integration into `vorpal/` is NOT done — this stays gated on your verdict.

**Outcome (fill in when done):** …

---

### [H-010] Phase 30 — TUI usability spot-check
**Added:** 2026-06-08  **Status:** open  *(pending Phase 30)*

**What to review / do:**
After Phase 30 lands: run `vorpal serve <some book>`. Complete a full
review → approve → build cycle using only the web UI (no CLI). Confirm it
feels usable and doesn't miss anything the CLI exposes.

**Decision options:**
- **Usable:** Phase 30 accepted as-is.
- **Missing something:** file specific gaps — the agent will add the missing
  surface to the UI.
- **Prefer CLI:** the UI is additive (CLI unchanged), so this is just a scope
  call on whether to invest further.

**Agent's assumption:** Phase 30 built and machine-tested. UI serves chapters
from `book.json`, edits persist, build streams via SSE. Full browser flow
not tested — assumed functional from unit tests; requires human spot-check.

Run: `pip install -e '.[web]'` then `vorpal serve <book.pdf>`.

**Outcome (fill in when done):** …

---

### [H-011] Phase 26 — Piper draft live speed test
**Added:** 2026-06-09  **Status:** open

**What to review / do:**
Install Piper on the host (or in the container via `docker/Dockerfile`) and
configure a model:

```
# Install piper binary
pip install piper-tts   # or download from github.com/rhasspy/piper/releases

# Download a fast English model (e.g. en_US-amy-low, ~15 MB)
wget https://github.com/rhasspy/piper/releases/download/v1.2.0/en_US-amy-low.onnx
export VORPAL_PIPER_MODEL=/path/to/en_US-amy-low.onnx

# Run a draft build and time it
time vorpal build scratch/outline.pdf --draft
```

Compare wall-clock time to a Kokoro-draft on the same machine (CPU).
The primary question: is Piper draft markedly faster than Kokoro draft on CPU?
Also confirm the audio is intelligible (not gibberish).

**Decision options:**
- **Piper is faster and intelligible:** Phase 26 fully accepted.
  Update docs/06-corpus.md with the timing results.
- **Piper is not available / crashes:** file the specific error — agent will
  investigate and fix.
- **Quality too poor even for drafts:** note it and the Piper fallback path
  remains as-implemented (Kokoro stays default).

**Agent's assumption:** Piper is not installed in the container (`shutil.which('piper')` returns None).
The engine code, fallback logic, and tests are complete. The `--draft` flag falls back
to Kokoro with a clear message. Live speed comparison deferred to operator.

**Outcome (fill in when done):** …

---

### [H-012] Phase 39 — Cast audition verdict (theatrical mode)
**Added:** 2026-06-09  **Status:** open

**What to review / do:**
Generate and listen to an audition of the Hamlet cast (GPU box, ~2 min of
audio across ~14 clips):

```
vorpal cast-audition corpus/plays/hamlet.txt
# → hamlet_audition/HAMLET.wav, KING.wav, OPHELIA.wav, …
```

Each non-cameo character gets one WAV with their 1–3 longest speeches in
their assigned voice. A tiny pre-made sample also exists from the Phase 38/39
acceptance runs: `scratch/pocket_trial_audition/ALICE.wav` (af_heart) and
`WHITE_RABBIT.wav` (bm_daniel).

Questions: do the principals sound distinct from each other? Does the
protagonist voice fit? Do any shared minor voices clash badly?

**Decision options:**
- **Casting is acceptable:** no action — `vorpal play <play> --approve`
  uses the same assignments.
- **Specific recast wanted:** either edit `<stem>_workdir/cast_sheet.json`
  (assignments map: character → voice id) or write a
  `cast_override.json` like `{"HAMLET": "bm_daniel"}` and pass
  `--cast-override` to both `cast-audition` (to re-listen) and `play`.
- **Casting algorithm itself is wrong** (e.g. systematically poor pairings):
  describe the pattern — agent will revise `vorpal/play/casting.py` rules.

**Agent's assumption:** the algorithmic cast (gender-matched, protagonist →
bm_george, unique voices for >50-line parts) is a reasonable default;
the full-Hamlet multi-voice synthesis is deferred until this verdict so a
4-hour build isn't burned on a cast nobody has heard.

**Outcome (fill in when done):** …

---

### [H-013] Phase 42 — Trotsky narrator voice verdict
**Added:** 2026-06-09  **Status:** open

**What to review / do:**
Listen to the 12 audition clips in `trotsky/audition/` (4 passages × 3
voices, 40–64 s each; regenerate any time with
`python scratch/trotsky_audition.py`):

- `blend_deep_steady_*` — Fenrir 55% + Michael 45% (the roadmap's pick)
- `am_fenrir_*` — Fenrir alone (deeper, more commanding)
- `bm_george_*` — George (the long-standing default narrator, British)

The four passages exercise the range of the prose: `polemical_opening`
(speech to the Moscow Soviet, March 1918), `analytical` (the author's
introduction on revolutionary violence), `address_to_soldiers` (the
Socialist Oath), `peroration` (the closing of "The International
Revolution").

Question: which voice should narrate all five production volumes?
(~30+ hours of audio — worth choosing carefully. Authority without
theatricality is the brief.)

**Decision options:**
- **Confirm `blend_deep_steady`:** no action — production builds (Phases
  43–45) already use it.
- **Prefer `am_fenrir` or `bm_george`:** note it here; the agent re-runs
  the volume builds with `--voice <id>` (the TTS cache makes only the
  voice change re-synthesize; mastering re-runs).
- **None fits:** name what's wrong (pace, depth, accent) — the agent will
  blend a new candidate and re-audition.

**Agent's assumption:** proceeded with `blend_deep_steady` per the roadmap
default ("declarative, urgent, highly structured — authority without
theatricality"). All five volumes will be built with it; a later voice swap
costs one re-synthesis pass per volume, nothing structural.

**Outcome (fill in when done):** …

---

### [H-019] Phase 43 — Stitching fix listening check (before/after)
**Added:** 2026-06-10  **Status:** open

**What to review / do:**
Listen to the paired clips (same 3-paragraph passage from the Trotsky v1
Introduction — analytically dense prose, the worst case for the artifact;
regenerate any time with `python scratch/phase43_stitch_ab.py`):

- `scratch/phase43_stitch_ab/before_phase43.wav` — pre-fix stitching
  (hard cuts + 50 ms silence at every chunk join)
- `scratch/phase43_stitch_ab/after_phase43.wav` — Phase 43 stitching
  (25 ms linear crossfade at sentence-boundary joins; paragraph gaps
  unchanged)

Question: in `before`, can you hear the narrator stop and restart at chunk
boundaries mid-paragraph (~every 22 s)? In `after`, are those same joins
inaudible?

*(Note: the roadmap suggested a Firestone excerpt; a Trotsky passage was
used instead because the artifact was observed on exactly this prose and
Phase 44 ships it — a strictly more relevant test.)*

**Decision options:**
- **Joins inaudible in `after`:** Phase 43 confirmed; nothing to do — all
  Trotsky production builds already use the fix (default `--crossfade-ms 25`).
- **Still audible:** note whether it's better/same/worse — the crossfade
  window is one CLI flag (`--crossfade-ms`, try 50–80) and re-stitching a
  built book is cheap (chunk cache untouched; delete `chapters/` and re-run).
- **Crossfade itself audible as a fade/blur:** lower `--crossfade-ms`
  (10–15) and re-stitch.

**Agent's assumption:** proceeded with the default 25 ms crossfade for all
Phase 44–46 production builds. Machine-side checks pass (correct output
length, no clipping, monotone blend ramp, silence at paragraph gaps); only
the perceptual verdict is open.

**Outcome (fill in when done):** …

---

## Closed items

*(Move entries here when addressed. Keep them for the record.)*

<!-- example:
### [H-000] Example closed item
**Added:** 2026-01-01  **Status:** ✅ done 2026-01-15
**Outcome:** Approved. Agent wired in the change in commit abc1234.
-->
