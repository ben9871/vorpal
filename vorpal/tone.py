"""Paragraph-level tone tagger — Phase 8.

Tags each paragraph in a chapter with a tone from the ≤ 8-tag vocabulary.
Results are cached per (chapter_text_hash, model, prompt_version) so a book
is tagged once, ever, unless the text or prompt version changes.

Two backends (see CLAUDE.md §Credentials):
  - "cli"  (default) — shells out to `claude -p`, which authenticates with the
    Claude Code subscription token (CLAUDE_CODE_OAUTH_TOKEN). Draws on the
    subscription you already pay for; needs no separate API balance. This is
    the default because the typical operator has subscription headroom but an
    empty pay-as-you-go API ledger.
  - "api"  (opt-in: --tone-backend api) — direct Anthropic SDK with
    VORPAL_ANTHROPIC_KEY. Pay-as-you-go; unlocks the Batches API discount.
    Use when you'd rather bill tagging to the API console than the subscription.
Everything behind --expressive; the deterministic no-tone build is untouched.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional


TONE_VOCAB = frozenset([
    "neutral", "somber", "tense", "warm", "wry",
    "excited", "urgent", "reflective",
])

PROMPT_VERSION = "v1"
DEFAULT_MODEL = "claude-haiku-4-5"
DEFAULT_BACKEND = "cli"     # "cli" = subscription via `claude -p`; "api" = pay-as-you-go SDK
MIN_RUN_LENGTH = 2          # isolated non-neutral spans < this → neutral
CONFIDENCE_THRESHOLD = 0.70  # below this, tag reverts to neutral

# ── prompt ────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a tone classifier for a literary audiobook narrator. \
Your job is to identify the dominant narrative tone of each paragraph \
so the narrator can deliver the book expressively. \
"neutral" must be the majority tag — only use non-neutral when the passage \
CLEARLY and unambiguously carries that tone. \
Vague emotional content → neutral."""

_USER_TEMPLATE = """\
Chapter: {chapter_title}

Classify each numbered paragraph with one of these tones:
  neutral    – everyday narration, no strong emotional colouring
  somber     – grief, loss, heaviness, melancholy
  tense      – suspense, conflict, rising stakes, controlled danger
  warm       – affection, comfort, nostalgia, gentle joy
  wry        – dry humour, irony, understated wit
  excited    – enthusiasm, wonder, discovery, anticipation
  urgent     – immediate danger, time pressure, desperation
  reflective – contemplation, memory, philosophical musing

Output ONLY a JSON array — one entry per paragraph, in order.
Each entry: {{"idx": 0, "tone": "neutral", "confidence": 0.95}}
Confidence is your certainty that this is the right tag (0.0–1.0).

Paragraphs:
{paragraphs}"""


def _resolve_key() -> Optional[str]:
    return (
        os.environ.get("VORPAL_ANTHROPIC_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
    )


def split_paragraphs(text: str) -> list:
    """Split body text into paragraphs (double-newline separated)."""
    paras = re.split(r"\n{2,}", text.strip())
    return [p.strip() for p in paras if p.strip()]


def _smooth_tones(tones: list, min_run: int = MIN_RUN_LENGTH) -> list:
    """Hysteresis: runs shorter than min_run get damped to neutral.

    A single isolated non-neutral paragraph surrounded by neutral paragraphs
    is almost always tonal noise from an over-eager tagger.
    """
    if not tones:
        return tones
    smoothed = list(tones)
    # Mark isolated spikes
    n = len(smoothed)
    i = 0
    while i < n:
        tone = smoothed[i]
        if tone == "neutral":
            i += 1
            continue
        # Find run end
        j = i
        while j < n and smoothed[j] == tone:
            j += 1
        run_len = j - i
        if run_len < min_run:
            for k in range(i, j):
                smoothed[k] = "neutral"
        i = j
    return smoothed


def _apply_confidence_gate(entries: list, threshold: float = CONFIDENCE_THRESHOLD) -> list:
    """Entries with confidence < threshold are set to neutral."""
    result = []
    for e in entries:
        if e.get("confidence", 1.0) < threshold:
            result.append({**e, "tone": "neutral"})
        else:
            result.append(e)
    return result


def _parse_llm_response(raw: str, n_paragraphs: int) -> list:
    """Extract the JSON array from the LLM response and validate it."""
    # Strip markdown code fences if present
    raw = re.sub(r"```(?:json)?", "", raw).strip()
    entries = json.loads(raw)
    if not isinstance(entries, list):
        raise ValueError("Expected a JSON array")
    # Validate each entry and normalise
    result = []
    for e in entries:
        tone = str(e.get("tone", "neutral")).lower().strip()
        if tone not in TONE_VOCAB:
            tone = "neutral"
        result.append({
            "idx": int(e.get("idx", len(result))),
            "tone": tone,
            "confidence": float(e.get("confidence", 1.0)),
        })
    # Fill gaps if the LLM returned fewer entries than paragraphs
    while len(result) < n_paragraphs:
        result.append({"idx": len(result), "tone": "neutral", "confidence": 1.0})
    return result[:n_paragraphs]


def _build_user_msg(paragraphs: list, chapter_title: str) -> str:
    numbered = "\n\n".join(f"[{i}] {p[:600]}" for i, p in enumerate(paragraphs))
    return _USER_TEMPLATE.format(
        chapter_title=chapter_title or "Unknown", paragraphs=numbered,
    )


# Map our canonical model IDs to the short aliases `claude -p --model` accepts.
_CLI_MODEL_ALIAS = {
    "claude-haiku-4-5": "haiku",
    "claude-sonnet-4-6": "sonnet",
    "claude-opus-4-8": "opus",
}


def _tag_paragraphs_api(paragraphs: list, chapter_title: str, model: str, client) -> list:
    """Direct Anthropic SDK (pay-as-you-go). Returns {idx, tone, confidence} entries."""
    response = client.messages.create(
        model=model,
        max_tokens=max(64, len(paragraphs) * 20),
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_user_msg(paragraphs, chapter_title)}],
    )
    raw = response.content[0].text
    return _parse_llm_response(raw, len(paragraphs))


def _tag_paragraphs_cli(paragraphs: list, chapter_title: str, model: str) -> list:
    """Shell out to `claude -p` (subscription-funded). Returns the same entries.

    The system prompt is prepended to the user message because `claude -p`
    has no separate system-prompt channel; the classifier instruction works
    fine as a preamble.
    """
    exe = shutil.which("claude")
    if not exe:
        raise RuntimeError(
            "tone backend 'cli' needs the `claude` CLI on PATH (the vorpal-box "
            "container has it). Install it, or use --tone-backend api."
        )
    alias = _CLI_MODEL_ALIAS.get(model, "haiku")
    prompt = (_SYSTEM_PROMPT + "\n\n"
              + _build_user_msg(paragraphs, chapter_title)
              + "\n\nReturn ONLY the JSON array, no prose, no code fence.")
    try:
        proc = subprocess.run(
            [exe, "-p", "--model", alias],
            input=prompt, capture_output=True, text=True,
            timeout=180, encoding="utf-8",
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("tone backend 'cli': `claude -p` timed out (180s)")
    if proc.returncode != 0:
        raise RuntimeError(
            f"tone backend 'cli': `claude -p` exited {proc.returncode}: "
            f"{(proc.stderr or '').strip()[:200]}"
        )
    return _parse_llm_response(proc.stdout, len(paragraphs))


def _chapter_cache_key(body: str, model: str, backend: str = DEFAULT_BACKEND) -> str:
    text_hash = hashlib.sha256(body.encode("utf-8", errors="replace")).hexdigest()[:16]
    # Backend is part of the key so switching backends re-tags rather than
    # silently mixing two providers' verdicts in one book.
    return f"{text_hash}_{model}_{backend}_{PROMPT_VERSION}"


def _tag_via_backend(paragraphs: list, title: str, model: str, backend: str) -> list:
    """Dispatch to the chosen backend; returns raw {idx, tone, confidence} entries."""
    if backend == "cli":
        return _tag_paragraphs_cli(paragraphs, title, model)
    if backend == "api":
        key = _resolve_key()
        if not key:
            raise RuntimeError(
                "tone backend 'api' requires VORPAL_ANTHROPIC_KEY — "
                "see CLAUDE.md §Credentials (or use the default --tone-backend cli)"
            )
        try:
            import anthropic
        except ImportError:
            raise RuntimeError("tone backend 'api' requires: pip install -e '.[llm]'")
        client = anthropic.Anthropic(api_key=key)
        return _tag_paragraphs_api(paragraphs, title, model, client)
    raise ValueError(f"unknown tone backend {backend!r} (expected 'cli' or 'api')")


def tag_chapter(body: str, title: str, cache_dir: Path,
                model: str = DEFAULT_MODEL, backend: str = DEFAULT_BACKEND) -> dict:
    """Tag paragraphs in a chapter and cache the result.

    Returns:
        {
          "chapter_title": str,
          "model": str,
          "prompt_version": str,
          "backend": str,
          "tones": ["neutral", "somber", ...],   # one per paragraph
          "paragraphs": [{idx, tone, confidence, text_preview}, ...],
          "cache_hit": bool,
        }

    backend "cli" (default) uses the subscription via `claude -p`; "api" uses
    the pay-as-you-go SDK with VORPAL_ANTHROPIC_KEY. Raises RuntimeError if the
    chosen backend is unavailable.
    """
    paragraphs = split_paragraphs(body)
    if not paragraphs:
        return {"chapter_title": title, "model": model,
                "prompt_version": PROMPT_VERSION, "backend": backend,
                "tones": [], "paragraphs": [], "cache_hit": False}

    cache_dir.mkdir(parents=True, exist_ok=True)
    ck = _chapter_cache_key(body, model, backend)
    cache_file = cache_dir / f"tone_{ck}.json"

    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            cached["cache_hit"] = True
            return cached
        except (json.JSONDecodeError, KeyError):
            pass  # corrupt cache — re-tag

    raw_entries = _tag_via_backend(paragraphs, title, model, backend)
    gated = _apply_confidence_gate(raw_entries)
    tones = _smooth_tones([e["tone"] for e in gated])

    result = {
        "chapter_title": title,
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "backend": backend,
        "tones": tones,
        "paragraphs": [
            {
                "idx": i,
                "tone": tones[i],
                "confidence": gated[i].get("confidence", 1.0),
                "text_preview": paragraphs[i][:80],
            }
            for i in range(len(paragraphs))
        ],
        "cache_hit": False,
    }
    cache_file.write_text(json.dumps(result, indent=2, ensure_ascii=False),
                          encoding="utf-8")
    return result


def tone_histogram(tones_per_chapter: list) -> dict:
    """Count tone occurrences across all chapters."""
    counts: dict = {t: 0 for t in TONE_VOCAB}
    for tones in tones_per_chapter:
        for t in tones:
            counts[t] = counts.get(t, 0) + 1
    total = sum(counts.values())
    return {"counts": counts, "total": total,
            "neutral_fraction": 1.0 if total == 0 else counts["neutral"] / total}
