"""EPUB input path: parse spine/TOC → sections with clean body text.

Converges at the segment-output interface: returns a list of section dicts
(compatible with Section.from_dict) with bodies stored inline.  No OCR, no
page geometry — EPUB ships structure intact so the full extract+segment
pipeline is bypassed.

Caller is responsible for converting dicts to Section objects so this module
stays free of circular imports (segment.chapters → extract.quality → OK,
but extract.epub → segment → extract would cycle at load time).
"""

import html
import html.parser
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


# ── HTML → plain text ────────────────────────────────────────────────────

_BLOCK_TAGS = frozenset(
    "p div h1 h2 h3 h4 h5 h6 br hr li tr blockquote section article".split()
)
_SKIP_TAGS = frozenset("script style aside nav".split())


class _TextExtractor(html.parser.HTMLParser):
    """Strip HTML tags; preserve paragraph breaks; skip nav/script/style."""

    def __init__(self):
        super().__init__()
        self.parts = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        if not self._skip_depth and tag in _BLOCK_TAGS:
            if self.parts and self.parts[-1] != "\n\n":
                self.parts.append("\n\n")

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        if not self._skip_depth and tag in _BLOCK_TAGS:
            if self.parts and self.parts[-1] != "\n\n":
                self.parts.append("\n\n")

    def handle_data(self, data):
        if not self._skip_depth:
            self.parts.append(data)

    def handle_entityref(self, name):
        if not self._skip_depth:
            self.parts.append(html.unescape(f"&{name};"))

    def handle_charref(self, name):
        if not self._skip_depth:
            self.parts.append(html.unescape(f"&#{name};"))

    def get_text(self) -> str:
        raw = "".join(self.parts)
        paragraphs = re.split(r"\n{2,}", raw)
        cleaned = []
        for p in paragraphs:
            p = re.sub(r"[ \t\r\f\v]+", " ", p).strip()
            if p:
                cleaned.append(p)
        return "\n\n".join(cleaned)


def _html_to_text(content: bytes) -> str:
    try:
        source = content.decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        source = content.decode("latin-1", errors="replace")
    parser = _TextExtractor()
    parser.feed(source)
    return parser.get_text()


# ── OPF / container parsing ───────────────────────────────────────────────

def _find_opf_path(zf: zipfile.ZipFile) -> str:
    container = zf.read("META-INF/container.xml").decode("utf-8", errors="replace")
    root = ET.fromstring(container)
    for elem in root.iter():
        if elem.tag.endswith("rootfile"):
            path = elem.get("full-path")
            if path:
                return path
    raise ValueError("No rootfile in META-INF/container.xml")


def _opf_dir(opf_path: str) -> str:
    idx = opf_path.rfind("/")
    return opf_path[:idx + 1] if idx >= 0 else ""


def _parse_opf(zf: zipfile.ZipFile, opf_path: str) -> dict:
    opf_dir = _opf_dir(opf_path)
    xml = zf.read(opf_path).decode("utf-8", errors="replace")
    root = ET.fromstring(xml)

    title = author = ""
    for elem in root.iter():
        local = elem.tag.rsplit("}", 1)[-1] if "}" in elem.tag else elem.tag
        if local == "title" and not title:
            title = (elem.text or "").strip()
        if local == "creator" and not author:
            author = (elem.text or "").strip()

    manifest = {}
    for item in root.iter():
        local = item.tag.rsplit("}", 1)[-1] if "}" in item.tag else item.tag
        if local == "item":
            item_id = item.get("id", "")
            href = item.get("href", "")
            media_type = item.get("media-type", "")
            props = item.get("properties", "")
            if href:
                manifest[item_id] = {
                    "href": opf_dir + href,
                    "media-type": media_type,
                    "properties": props,
                }

    spine_idrefs = []
    for itemref in root.iter():
        local = itemref.tag.rsplit("}", 1)[-1] if "}" in itemref.tag else itemref.tag
        if local == "itemref":
            if itemref.get("linear", "yes").lower() != "no":
                spine_idrefs.append(itemref.get("idref", ""))

    nav_id = ncx_id = None
    for item_id, item in manifest.items():
        if "nav" in item.get("properties", ""):
            nav_id = item_id
        if item["media-type"] == "application/x-dtbncx+xml":
            ncx_id = item_id

    spine_hrefs = [manifest[idref]["href"]
                   for idref in spine_idrefs if idref in manifest]

    return {
        "title": title, "author": author,
        "spine_hrefs": spine_hrefs,
        "manifest": manifest,
        "nav_id": nav_id, "ncx_id": ncx_id,
        "opf_dir": opf_dir,
    }


# ── TOC parsing ───────────────────────────────────────────────────────────

def _parse_nav(zf: zipfile.ZipFile, nav_href: str) -> list:
    """EPUB3 nav → [(title, href), ...] for the toc nav element."""
    xml = zf.read(nav_href).decode("utf-8", errors="replace")
    root = ET.fromstring(xml)
    entries = []
    for nav in root.iter():
        local = nav.tag.rsplit("}", 1)[-1] if "}" in nav.tag else nav.tag
        if local != "nav":
            continue
        etype = nav.get("{http://www.idpf.org/2007/ops}type", nav.get("epub:type", ""))
        if "toc" not in etype:
            continue
        for a in nav.iter():
            local_a = a.tag.rsplit("}", 1)[-1] if "}" in a.tag else a.tag
            if local_a == "a":
                href = a.get("href", "")
                text = "".join(a.itertext()).strip()
                if text and href:
                    entries.append((text, href))
    return entries


def _parse_ncx(zf: zipfile.ZipFile, ncx_href: str) -> list:
    """EPUB2 NCX → [(title, content_src), ...] for all navPoints (all depths)."""
    ncx_dir = _opf_dir(ncx_href)
    xml = zf.read(ncx_href).decode("utf-8", errors="replace")
    root = ET.fromstring(xml)
    entries = []
    for navPoint in root.iter():
        local = navPoint.tag.rsplit("}", 1)[-1] if "}" in navPoint.tag else navPoint.tag
        if local != "navPoint":
            continue
        title = src = ""
        for child in navPoint:
            child_local = child.tag.rsplit("}", 1)[-1] if "}" in child.tag else child.tag
            if child_local == "navLabel":
                for t in child.iter():
                    t_local = t.tag.rsplit("}", 1)[-1] if "}" in t.tag else t.tag
                    if t_local == "text":
                        title = (t.text or "").strip()
            if child_local == "content":
                raw = child.get("src", "")
                src = ncx_dir + raw if raw else ""
        if title and src:
            entries.append((title, src))
    return entries


def _href_base(href: str) -> str:
    """Strip fragment and normalise path separators."""
    base = href.split("#")[0] if "#" in href else href
    return base.lstrip("/")


def _toc_to_spine_map(spine_hrefs: list, toc_entries: list) -> dict:
    """Map spine index → title for every TOC entry that can be matched."""
    result = {}
    for title, href in toc_entries:
        base = _href_base(href)
        for i, sh in enumerate(spine_hrefs):
            sh_base = _href_base(sh)
            if sh_base == base or sh_base.endswith("/" + base) or base.endswith("/" + sh_base):
                if i not in result:
                    result[i] = title
                break
    return result


# ── main entry point ──────────────────────────────────────────────────────

def extract_epub(epub_path: Path) -> dict:
    """Parse an EPUB file into section dicts ready for the pipeline.

    Returns:
        {
          "title": str,
          "author": str,
          "format": "epub",
          "sections": [section_dict, ...],   # compatible with Section.from_dict
          "qa": dict,
        }

    Each section dict has ``body`` populated and ``source = "spine"``.
    """
    with zipfile.ZipFile(str(epub_path), "r") as zf:
        opf_path = _find_opf_path(zf)
        opf = _parse_opf(zf, opf_path)

        # Extract text for every spine item
        spine_texts = {}
        for href in opf["spine_hrefs"]:
            try:
                raw = zf.read(href)
                spine_texts[href] = _html_to_text(raw)
            except KeyError:
                spine_texts[href] = ""

        # Build title map from NAV (EPUB3) or NCX (EPUB2)
        toc_entries = []
        if opf["nav_id"] and opf["nav_id"] in opf["manifest"]:
            nav_href = opf["manifest"][opf["nav_id"]]["href"]
            toc_entries = _parse_nav(zf, nav_href)
        if not toc_entries and opf["ncx_id"] and opf["ncx_id"] in opf["manifest"]:
            ncx_href = opf["manifest"][opf["ncx_id"]]["href"]
            toc_entries = _parse_ncx(zf, ncx_href)

    spine_hrefs = opf["spine_hrefs"]
    spine_title_map = _toc_to_spine_map(spine_hrefs, toc_entries)

    # Merge untitled spine items into the preceding titled section
    raw_sections = []          # [(title, [text_parts])]
    for i, href in enumerate(spine_hrefs):
        text = spine_texts.get(href, "").strip()
        if not text:
            continue
        if i in spine_title_map:
            raw_sections.append((spine_title_map[i], [text]))
        elif raw_sections:
            raw_sections[-1][1].append(text)
        else:
            raw_sections.append(("Introduction", [text]))

    # If TOC gave us nothing (no nav/NCX), treat each non-empty spine item as a section
    if not raw_sections:
        raw_sections = [
            (f"Section {i + 1}", [spine_texts[href]])
            for i, href in enumerate(spine_hrefs)
            if spine_texts.get(href, "").strip()
        ]

    # Build section dicts
    sections = []
    chapter_no = 0
    for idx, (title, parts) in enumerate(raw_sections):
        body = "\n\n".join(parts).strip()
        words = len(body.split())
        kind = _classify_title(title)
        include = kind == "chapter"
        if include:
            chapter_no += 1
            display = _strip_enum_prefix(title)
            spoken_intro = f"Chapter {_spoken_num(chapter_no)}. {display}."
        else:
            spoken_intro = _strip_enum_prefix(title) + "."

        flags = []
        if words < 100 and include:
            flags.append("short-body")

        sections.append({
            "id": idx + 1,
            "title": title,
            "kind": kind,
            "include": include,
            "spoken_intro": spoken_intro,
            "start": [idx, 0],
            "end": [idx, 0],
            "pages": [idx + 1, idx + 1],
            "source": "spine",
            "confidence": 1.0,
            "words": words,
            "flags": flags,
            "body": body,
        })

    qa = {
        "spine_items": len(spine_hrefs),
        "toc_entries": len(toc_entries),
        "sections_produced": len(sections),
        "chapter_source": "spine",
    }

    return {
        "title": opf["title"],
        "author": opf["author"],
        "format": "epub",
        "sections": sections,
        "qa": qa,
    }


# ── helpers (local copies to avoid import cycle with segment) ─────────────

_ONES = "zero one two three four five six seven eight nine ten eleven twelve \
thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
_TENS = ["", "", "twenty", "thirty", "forty", "fifty"]

_ENUM_RE = re.compile(
    r"^\s*(?:chapter|part|section)?\s*(?:\d{1,3}|[IVXLCDM]+(?![A-Za-z]))\s*[.):—-]?\s*",
    re.IGNORECASE,
)

_FRONT_KEYWORDS = frozenset([
    "preface", "foreword", "introduction", "acknowledgements", "acknowledgments",
    "prologue", "copyright", "dedication", "epigraph", "author's note",
    "note to the reader",
])
_FRONT_PREFIXES = ("about the author", "author note")

_BACK_KEYWORDS = frozenset([
    "index", "bibliography", "notes", "afterword", "appendix", "glossary",
    "further reading", "references", "selected works", "works cited",
])
# Note: a bare "about " prefix is too greedy — it swallowed real chapters
# ("About the ex-Officers", "About the Organisation of Labour" in Trotsky's
# Military Writings, found by the Phase 41 fidelity audit).  Only
# publisher/edition material qualifies.
_BACK_PREFIXES = ("about the publisher", "about the translator",
                  "about this ", "appendix ")


def _spoken_num(n: int) -> str:
    if n < 20:
        return _ONES[n]
    if n < 60:
        tens, ones = divmod(n, 10)
        return _TENS[tens] + (f"-{_ONES[ones]}" if ones else "")
    return str(n)


def _strip_enum_prefix(title: str) -> str:
    stripped = _ENUM_RE.sub("", title.strip())
    return stripped if stripped else title.strip()


def _classify_title(title: str) -> str:
    t_clean = re.sub(r"[^a-z ]", "", title.lower().strip()).strip()
    if t_clean in _FRONT_KEYWORDS or any(t_clean.startswith(p) for p in _FRONT_PREFIXES):
        return "frontmatter"
    if t_clean in _BACK_KEYWORDS or any(t_clean.startswith(p) for p in _BACK_PREFIXES):
        return "backmatter"
    # Project Gutenberg license / boilerplate sections
    if "project gutenberg" in t_clean:
        return "backmatter"
    return "chapter"
