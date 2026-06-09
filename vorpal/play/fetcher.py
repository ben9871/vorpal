"""Project Gutenberg play downloader.

Downloads a Gutenberg plain-text play by title or numeric ID, strips the
standard PG boilerplate header/footer, and saves to corpus/plays/<slug>.txt.
"""

import re
import urllib.request
from pathlib import Path

# Hardcoded catalogue: title slug → Gutenberg book ID
CATALOGUE: dict = {
    "hamlet": 1524,
    "midsummer": 1514,
    "midsummer-nights-dream": 1514,
    "a-midsummer-nights-dream": 1514,
    "macbeth": 1533,
    # PG #1523 is As You Like It, not Twelfth Night — found in the Phase 40
    # corpus run (the roadmap's guess was wrong). Twelfth Night is #1526.
    "twelfth-night": 1526,
    "as-you-like-it": 1523,
    "the-tempest": 23042,
    "tempest": 23042,
    "much-ado": 1882,
    "much-ado-about-nothing": 1882,
    "the-importance-of-being-earnest": 844,
    "earnest": 844,
}

# Canonical PG boilerplate boundary strings (regex patterns)
_START_RE = re.compile(
    r"\*{3}\s*START OF (THE |THIS )?PROJECT GUTENBERG",
    re.IGNORECASE,
)
_END_RE = re.compile(
    r"\*{3}\s*END OF (THE |THIS )?PROJECT GUTENBERG",
    re.IGNORECASE,
)

# Gutenberg plain-text URL templates (tried in order)
_URL_TEMPLATES = [
    "https://gutenberg.org/cache/epub/{id}/pg{id}.txt",
    "https://www.gutenberg.org/files/{id}/{id}-0.txt",
    "https://www.gutenberg.org/files/{id}/{id}.txt",
]


def _slug(title_or_id: str) -> str:
    """Normalise a title string to a catalogue key slug."""
    return re.sub(r"[^a-z0-9]+", "-", title_or_id.lower()).strip("-")


def _resolve_id(title_or_id: str) -> tuple:
    """Return (book_id, slug) for the given title or numeric ID."""
    if re.match(r"^\d+$", title_or_id.strip()):
        bid = int(title_or_id.strip())
        slug = str(bid)
        # Check catalogue for a named slug
        for k, v in CATALOGUE.items():
            if v == bid:
                slug = k
                break
        return bid, slug

    slug = _slug(title_or_id)
    if slug not in CATALOGUE:
        raise ValueError(
            f"Unknown play {title_or_id!r}. Known titles: {list(CATALOGUE.keys())}"
        )
    return CATALOGUE[slug], slug


def strip_pg_boilerplate(text: str) -> str:
    """Remove the standard Project Gutenberg header and footer."""
    start_m = _START_RE.search(text)
    if start_m:
        # Advance past the rest of the *** line ***
        after_start = text[start_m.end():]
        # Skip to end of that marker line
        nl = after_start.find("\n")
        text = after_start[nl + 1:] if nl != -1 else after_start

    end_m = _END_RE.search(text)
    if end_m:
        text = text[: end_m.start()]

    return text.strip()


def fetch_play(
    title_or_id: str,
    corpus_dir: Path = Path("corpus/plays"),
) -> Path:
    """Download a Gutenberg play, strip boilerplate, save to corpus_dir.

    Returns the path to the saved .txt file.
    Raises ValueError for unknown titles, RuntimeError on download failure.
    """
    book_id, slug = _resolve_id(title_or_id)
    corpus_dir = Path(corpus_dir)
    corpus_dir.mkdir(parents=True, exist_ok=True)
    dest = corpus_dir / f"{slug}.txt"

    errors = []
    for template in _URL_TEMPLATES:
        url = template.format(id=book_id)
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "vorpal-play-fetcher/1.0 (project gutenberg download)"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw_bytes = resp.read()
            # Gutenberg files are UTF-8 with BOM or latin-1
            try:
                text = raw_bytes.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = raw_bytes.decode("latin-1")
            stripped = strip_pg_boilerplate(text)
            dest.write_text(stripped, encoding="utf-8")
            return dest
        except Exception as exc:
            errors.append(f"{url}: {exc}")
            continue

    raise RuntimeError(
        f"Failed to download play ID {book_id} after trying all URL templates.\n"
        + "\n".join(errors)
    )
