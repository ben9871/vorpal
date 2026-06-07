"""Pronunciation lexicon — per-book name/term overrides — Phase 13.

An optional LLM pass proposes spoken forms for proper nouns the TTS might
render oddly.  Entries are stored in manifest.data["lexicon"] and applied
(in normalize.py) only for approved entries.

Deterministic core untouched: building without --lexicon produces byte-identical
output.  The lexicon only changes text that was already going to TTS.

Entry schema:
  { "word": str,        # exact form as it appears in the text
    "spoken_form": str, # plain-English pronunciation hint, e.g. "fire stone"
    "approved": bool }  # False until the human (or --approve) confirms it

Typical flow:
  vorpal build book.pdf --lexicon          # propose + store (not applied yet)
  vorpal review book.pdf --lexicon         # inspect, edit spoken_form, approve
  vorpal build book.pdf --lexicon          # re-run; approved entries are applied
"""

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional


PROMPT_VERSION = "v1"
_MAX_WORDS_FOR_PROPOSAL = 100   # cap: send at most this many candidate words to LLM


# ── proper-noun extraction ───────────────────────────────────────────────────


def extract_proper_nouns(text: str) -> list:
    """Return a deduplicated list of candidate proper nouns from body text.

    Heuristic: capitalized words/phrases that are not sentence-initial.
    Returns the candidates as a sorted list of strings.
    """
    # Split into sentences (cheap: just look for .?! followed by space+capital)
    # Then find capitalized runs not at the start of a sentence.
    sentences = re.split(r'(?<=[.!?])\s+', text)
    candidates = set()
    for sent in sentences:
        words = sent.split()
        if not words:
            continue
        # Skip the very first word (it's capitalized by sentence convention)
        for word in words[1:]:
            # Allow hyphenated names like "Marx-Engels"
            core = re.sub(r"[^\w-]", "", word)
            if not core:
                continue
            if core[0].isupper() and len(core) >= 3 and not core.isupper():
                candidates.add(core)

    # Filter out very common words that happen to be capitalized mid-sentence
    _COMMON_CAPS = frozenset([
        "The", "A", "An", "And", "But", "Or", "For", "Nor", "So", "Yet",
        "As", "At", "By", "In", "Is", "It", "Of", "On", "To", "Up",
        "This", "That", "These", "Those", "They", "He", "She", "We", "You",
        "I", "My", "His", "Her", "Their", "Our", "Its",
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
        "Saturday", "Sunday",
        "American", "British", "English", "French", "German",
        "Western", "Eastern", "Northern", "Southern",
        "New", "Old", "First", "Last",
    ])
    candidates -= _COMMON_CAPS
    return sorted(candidates)[:_MAX_WORDS_FOR_PROPOSAL]


# ── LLM proposal ────────────────────────────────────────────────────────────


_SYSTEM_PROMPT = """\
You are a TTS pronunciation assistant for an audiobook pipeline. \
Given a list of proper nouns from a non-fiction book, identify ones a \
text-to-speech system might mispronounce, and suggest a plain-English \
spoken form. Only flag genuinely tricky words; skip obvious ones. \
Use hyphens to show syllable breaks: "Shulamith" → "Shoo-lah-mith". \
Output ONLY a JSON array."""

_USER_TEMPLATE = """\
Book: {title}

Proper nouns found in the text (one per line):
{word_list}

For each word you think needs a pronunciation hint, output:
{{"word": "original", "spoken_form": "how-to-say-it"}}

Skip obvious words (Marx, Engels, chapter numbers, common names).
Output ONLY a JSON array, possibly empty []."""


def _cache_key(word_list: list, title: str) -> str:
    blob = json.dumps({"words": sorted(word_list), "title": title,
                       "v": PROMPT_VERSION}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def propose_lexicon(
    body_text: str,
    title: str,
    cache_dir: Path,
    model: str = "claude-haiku-4-5",
    backend: str = "cli",
) -> list:
    """LLM pass: propose pronunciation entries for the book's proper nouns.

    Returns a list of {word, spoken_form, approved=False} dicts.
    Caches by (word_list, title, prompt_version) so repeated calls are free.
    Returns [] when no proper nouns need hints (LLM or cache may return empty).
    """
    candidates = extract_proper_nouns(body_text)
    if not candidates:
        return []

    cache_dir.mkdir(parents=True, exist_ok=True)
    ck = _cache_key(candidates, title)
    cache_file = cache_dir / f"lexicon_{ck}.json"

    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    word_list_str = "\n".join(candidates)
    user_msg = _USER_TEMPLATE.format(title=title or "Unknown", word_list=word_list_str)

    raw = _call_backend(user_msg, model, backend)
    entries = _parse_proposal(raw)

    cache_file.write_text(json.dumps(entries, indent=2, ensure_ascii=False),
                          encoding="utf-8")
    return entries


def _call_backend(user_msg: str, model: str, backend: str) -> str:
    """Call the LLM and return the raw text response."""
    from .tone import _CLI_MODEL_ALIAS

    if backend == "api":
        key = _resolve_key()
        if not key:
            raise RuntimeError(
                "lexicon backend 'api' requires VORPAL_ANTHROPIC_KEY — "
                "see CLAUDE.md §Credentials"
            )
        try:
            import anthropic
        except ImportError:
            raise RuntimeError("lexicon backend 'api' requires: pip install -e '.[llm]'")
        client = anthropic.Anthropic(api_key=key)
        resp = client.messages.create(
            model=model,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        return resp.content[0].text

    if backend == "cli":
        exe = shutil.which("claude")
        if not exe:
            raise RuntimeError(
                "lexicon backend 'cli' needs `claude` on PATH "
                "(vorpal-box has it; or use --lexicon-backend api)"
            )
        alias = _CLI_MODEL_ALIAS.get(model, "haiku")
        full_prompt = (_SYSTEM_PROMPT + "\n\n" + user_msg
                       + "\n\nReturn ONLY the JSON array.")
        proc = subprocess.run(
            [exe, "-p", "--model", alias],
            input=full_prompt, capture_output=True, text=True,
            timeout=120, encoding="utf-8",
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"lexicon backend 'cli': `claude -p` exited {proc.returncode}: "
                f"{(proc.stderr or '').strip()[:200]}"
            )
        return proc.stdout

    raise ValueError(f"unknown lexicon backend {backend!r}")


def _parse_proposal(raw: str) -> list:
    """Parse the LLM JSON response into [{word, spoken_form, approved}]."""
    raw = re.sub(r"```(?:json)?", "", raw).strip()
    try:
        items = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(items, list):
        return []
    result = []
    for item in items:
        word = str(item.get("word", "")).strip()
        spoken = str(item.get("spoken_form", "")).strip()
        if word and spoken and word != spoken:
            result.append({"word": word, "spoken_form": spoken, "approved": False})
    return result


def _resolve_key() -> Optional[str]:
    import os
    return (os.environ.get("VORPAL_ANTHROPIC_KEY")
            or os.environ.get("ANTHROPIC_API_KEY"))


# ── lexicon application (normalize step) ─────────────────────────────────────


def apply_lexicon_to_text(text: str, lexicon_entries: list) -> str:
    """Replace approved lexicon words with their spoken forms.

    Matches whole words only (word-boundary regex).  Only entries with
    approved=True are applied.  The substitution preserves the surrounding
    text so normalization can continue.

    Returns the original text unchanged when no entries are approved.
    """
    approved = [(e["word"], e["spoken_form"])
                for e in lexicon_entries
                if e.get("approved") and e.get("word") and e.get("spoken_form")]
    if not approved:
        return text

    # Sort by word length descending so longer forms match first
    approved.sort(key=lambda x: -len(x[0]))
    for word, spoken in approved:
        pattern = r'\b' + re.escape(word) + r'\b'
        text = re.sub(pattern, spoken, text)
    return text


# ── manifest helpers ──────────────────────────────────────────────────────────


def merge_lexicon(existing: list, proposed: list) -> list:
    """Merge proposed entries into the existing lexicon.

    New words are added (approved=False); existing approved entries are
    preserved unchanged; existing un-approved entries may be updated if
    the proposed spoken_form changed.
    """
    existing_by_word = {e["word"]: e for e in existing}
    for prop in proposed:
        word = prop["word"]
        if word not in existing_by_word:
            existing_by_word[word] = prop
        elif not existing_by_word[word].get("approved", False):
            # Update spoken_form if not yet approved
            existing_by_word[word]["spoken_form"] = prop["spoken_form"]
    return list(existing_by_word.values())
