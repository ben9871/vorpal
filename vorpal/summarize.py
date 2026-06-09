"""Chapter summary side product — Phase 29.

Generates one-paragraph summaries per chapter via the LLM backend (same
backends as tone.py: 'cli' uses the subscription, 'api' uses VORPAL_ANTHROPIC_KEY).

Content-fidelity contract: summaries are never injected into TTS text, never
narrated, never included in any audio chunk. They are a separate textual
side product stored in the manifest and emitted as summaries.md.

Cache: keyed on (chapter_text_hash, model, prompt_version) — a chapter is
summarised exactly once. Changing the model or prompt version invalidates
the cache for that chapter.

Manual-seeding protocol: when LLM credentials are absent or for testing,
call inject_manual_summary() to write a hand-crafted summary into the cache.
The pipeline then reads it as a normal cache hit.
"""

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Optional

PROMPT_VERSION = "v1"
DEFAULT_MODEL = "claude-haiku-4-5"
DEFAULT_BACKEND = "cli"


def _text_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8", errors="replace")).hexdigest()[:16]


def _cache_key(body: str, model: str, backend: str = DEFAULT_BACKEND) -> str:
    return f"{_text_hash(body)}_{model}_{backend}_{PROMPT_VERSION}"


def _cache_path(cache_dir: Path, body: str, model: str,
                backend: str = DEFAULT_BACKEND) -> Path:
    ck = _cache_key(body, model, backend)
    return cache_dir / f"summary_{ck}.json"


_SUMMARY_PROMPT = """\
Write a single paragraph (3-5 sentences) summarising the following book chapter. \
Focus on what happens and what is established — not style or narration. \
Be concise and factual. Do not include any introductory phrase like "In this chapter…". \
Return only the paragraph, nothing else.

CHAPTER: {title}

TEXT:
{body}
"""


def _summarize_via_cli(body: str, title: str, model: str) -> Optional[str]:
    """Call `claude -p` and return the summary text, or None on failure."""
    prompt = _SUMMARY_PROMPT.format(title=title, body=body[:4000])
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--model", model],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            return None
        text = result.stdout.strip()
        return text if text else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _summarize_via_api(body: str, title: str, model: str) -> Optional[str]:
    """Summarize via the pay-as-you-go API using VORPAL_ANTHROPIC_KEY."""
    import os
    key = (os.environ.get("VORPAL_ANTHROPIC_KEY")
           or os.environ.get("ANTHROPIC_API_KEY"))
    if not key:
        raise RuntimeError(
            "summary backend 'api' requires VORPAL_ANTHROPIC_KEY — "
            "see CLAUDE.md §Credentials (or use the default --summaries-backend cli)"
        )
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("summary backend 'api' requires: pip install -e '.[llm]'")
    client = anthropic.Anthropic(api_key=key)
    prompt = _SUMMARY_PROMPT.format(title=title, body=body[:4000])
    msg = client.messages.create(
        model=model,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text.strip() if msg.content else ""
    return text if text else None


def summarize_chapter(
    body: str, title: str, cache_dir: Path,
    model: str = DEFAULT_MODEL, backend: str = DEFAULT_BACKEND,
) -> dict:
    """Generate (or load from cache) a one-paragraph summary for a chapter.

    Returns:
        {
          "chapter_title": str,
          "model": str,
          "prompt_version": str,
          "backend": str,
          "summary": str or None,   # None = blocked / unavailable
          "cache_hit": bool,
          "blocked": bool,
        }

    When blocked=True the summary is None and the chapter is skipped silently.
    """
    base = {"chapter_title": title, "model": model,
            "prompt_version": PROMPT_VERSION, "backend": backend}

    if not body.strip():
        return {**base, "summary": None, "cache_hit": False, "blocked": True}

    cache_dir.mkdir(parents=True, exist_ok=True)
    cp = _cache_path(cache_dir, body, model, backend)

    if cp.exists():
        try:
            data = json.loads(cp.read_text(encoding="utf-8"))
            data["cache_hit"] = True
            return data
        except Exception:
            pass

    # Try to generate
    try:
        if backend == "cli":
            text = _summarize_via_cli(body, title, model)
        elif backend == "api":
            text = _summarize_via_api(body, title, model)
        else:
            raise ValueError(f"unknown backend {backend!r}")
    except RuntimeError as e:
        return {**base, "summary": None, "cache_hit": False,
                "blocked": True, "block_reason": str(e)}

    if text is None:
        return {**base, "summary": None, "cache_hit": False, "blocked": True}

    result = {**base, "summary": text, "cache_hit": False, "blocked": False}
    cp.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def inject_manual_summary(cache_dir: Path, body: str, title: str, summary: str,
                           model: str = DEFAULT_MODEL,
                           backend: str = DEFAULT_BACKEND) -> Path:
    """Write a manually-authored summary into the cache.

    Use when LLM credentials are absent (manual-seeding protocol).  Once
    injected, summarize_chapter() returns this as a cache hit.
    Returns the cache file path.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    cp = _cache_path(cache_dir, body, model, backend)
    result = {
        "chapter_title": title, "model": model,
        "prompt_version": PROMPT_VERSION, "backend": backend,
        "summary": summary, "cache_hit": False, "blocked": False,
    }
    cp.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return cp


def generate_summaries_md(
    summaries: list, book_title: str = ""
) -> str:
    """Format summaries as a Markdown side product.

    summaries: list of dicts from summarize_chapter(), one per included chapter.
    Returns the full summaries.md text.  Blocked/None summaries are omitted.
    """
    lines = []
    if book_title:
        lines.append(f"# Summaries — {book_title}\n")
    else:
        lines.append("# Chapter Summaries\n")

    has_any = False
    for s in summaries:
        text = s.get("summary")
        if not text:
            continue
        has_any = True
        title = s.get("chapter_title", "")
        lines.append(f"## {title}\n")
        lines.append(f"{text}\n")
        lines.append("---\n")

    if not has_any:
        lines.append(
            "*No summaries generated — run with `--summaries` and LLM credentials.*\n"
        )

    return "\n".join(lines)
