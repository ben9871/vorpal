"""Text fidelity QA: compare pipeline output against the source file.

Arc 8 contract: every narrable word in the source must reach the
synthesizer.  This module checks that the chapter texts written during the
segment stage (``<workdir>/chapter_texts/*.txt``) faithfully reproduce the
source document's text.

Source side:
- EPUB: one string per OPF spine item (same ``_html_to_text`` extractor the
  pipeline itself uses, so a perfect pipeline scores 1.0)
- PDF:  one string per page from the embedded text layer (born-digital PDFs;
  scanned PDFs without a text layer yield empty source items and the caller
  should fall back to OCR-confidence checks instead)
- TXT:  the whole file as a single source item

Workdir side: ``chapter_texts/*.txt`` in filename order (the ``NN_`` id
prefix preserves narration order).

Alignment: each workdir chapter is greedily matched to a contiguous run of
source items (sections legitimately merge several spine items; PDF chapters
span several pages).  Similarity is a difflib ratio over normalized word
streams.  Note: on PDFs, chapter boundaries mid-page shave the score at the
edges — the dropped-paragraph count is the stronger signal there.
"""

import re
import zipfile
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional

# Thresholds from the roadmap (Arc 8, Phase 41)
PASS_THRESHOLD = 0.90
DEGRADED_THRESHOLD = 0.70

# Paragraphs shorter than this (in words) are too generic to count as
# evidence of dropped text (headings, dates, "***" separators).
MIN_DROP_PARAGRAPH_WORDS = 8


# ── data model ────────────────────────────────────────────────────────────

@dataclass
class ChapterFidelity:
    chapter: str                      # workdir filename stem
    similarity: float                 # difflib ratio vs matched source span
    matched_source: List[str]         # source item ids in the matched span
    dropped_paragraphs: List[str]     # source paragraphs absent from output

    @property
    def status(self) -> str:
        if self.similarity >= PASS_THRESHOLD:
            return "pass"
        if self.similarity >= DEGRADED_THRESHOLD:
            return "degraded"
        return "fail"


@dataclass
class FidelityReport:
    chapters: List[ChapterFidelity] = field(default_factory=list)
    unmatched_source: List[str] = field(default_factory=list)  # source ids
    order_anomalies: List[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        """passed | degraded | failed (roadmap thresholds)."""
        if not self.chapters:
            return "failed"
        worst = min(c.similarity for c in self.chapters)
        if worst < DEGRADED_THRESHOLD:
            return "failed"
        if worst < PASS_THRESHOLD:
            return "degraded"
        return "passed"

    @property
    def total_dropped(self) -> int:
        return sum(len(c.dropped_paragraphs) for c in self.chapters)


# ── source extraction ─────────────────────────────────────────────────────

def extract_epub_chapter_texts(epub_path: Path) -> Dict[str, str]:
    """One plain-text string per OPF spine item, in spine order.

    Uses the same HTML→text extractor as the pipeline's EPUB path so that
    differences reflect pipeline behavior, not extractor drift.
    """
    from ..extract.epub import _find_opf_path, _parse_opf, _html_to_text

    texts: Dict[str, str] = {}
    with zipfile.ZipFile(str(epub_path), "r") as zf:
        opf = _parse_opf(zf, _find_opf_path(zf))
        for href in opf["spine_hrefs"]:
            try:
                raw = zf.read(href)
            except KeyError:
                texts[href] = ""
                continue
            texts[href] = _html_to_text(raw)
    return texts


def extract_pdf_chapter_texts(pdf_path: Path) -> Dict[str, str]:
    """One string per page from the PDF's embedded text layer."""
    import fitz

    texts: Dict[str, str] = {}
    doc = fitz.open(str(pdf_path))
    try:
        for i in range(len(doc)):
            texts[f"page_{i + 1:04d}"] = doc[i].get_text()
    finally:
        doc.close()
    return texts


def extract_txt_chapter_texts(txt_path: Path) -> Dict[str, str]:
    """The whole TXT file as a single source item."""
    return {txt_path.name: txt_path.read_text(encoding="utf-8", errors="replace")}


def extract_source_texts(source_path: Path) -> Dict[str, str]:
    """Dispatch on extension: EPUB spine items / PDF pages / TXT whole-file."""
    suffix = source_path.suffix.lower()
    if suffix == ".epub":
        return extract_epub_chapter_texts(source_path)
    if suffix == ".pdf":
        return extract_pdf_chapter_texts(source_path)
    if suffix in (".txt", ".text"):
        return extract_txt_chapter_texts(source_path)
    raise ValueError(f"Unsupported source format for fidelity check: {suffix!r}")


def extract_workdir_chapter_texts(work_dir: Path) -> Dict[str, str]:
    """Read ``chapter_texts/*.txt`` in filename order (id prefix = order)."""
    body_dir = Path(work_dir) / "chapter_texts"
    if not body_dir.is_dir():
        return {}
    texts: Dict[str, str] = {}
    for path in sorted(body_dir.glob("*.txt")):
        texts[path.stem] = path.read_text(encoding="utf-8", errors="replace")
    return texts


# ── comparison ────────────────────────────────────────────────────────────

_WORD_RE = re.compile(r"[a-z0-9']+")


def _norm_words(text: str) -> List[str]:
    return _WORD_RE.findall(text.lower())


def _ratio(a: List[str], b: List[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    sm = SequenceMatcher(None, a, b, autojunk=False)
    if sm.real_quick_ratio() < 0.1:
        return sm.real_quick_ratio()
    return sm.ratio()


# How many candidate start items get the full greedy extension.  Ranking
# is by cheap quick_ratio; the full ratio is only computed during extension.
_MAX_START_CANDIDATES = 8


def _best_span(source_ids: List[str], source_words: Dict[str, List[str]],
               chapter_words: List[str]) -> (float, List[int]):
    """Greedy alignment: try the most promising starting source items and
    extend each forward while the ratio improves; keep the best span.
    (A single best-start pick is wrong when a chapter concatenates several
    items and a later item alone outscores the true first item.)"""
    if not source_ids:
        return 0.0, []
    scored = []
    for idx, sid in enumerate(source_ids):
        sm = SequenceMatcher(None, source_words[sid], chapter_words,
                             autojunk=False)
        scored.append((sm.quick_ratio(), idx))
    scored.sort(key=lambda t: (-t[0], t[1]))
    candidates = [idx for _, idx in scored[:_MAX_START_CANDIDATES]]

    best_r, best_span = -1.0, []
    for start in candidates:
        acc = list(source_words[source_ids[start]])
        r = _ratio(acc, chapter_words)
        span = [start]
        j = start + 1
        while j < len(source_ids):
            cand = acc + source_words[source_ids[j]]
            r2 = _ratio(cand, chapter_words)
            if r2 > r + 1e-9:
                r, acc = r2, cand
                span.append(j)
                j += 1
            else:
                break
        # Backward extension: a small stub item merged in *before* the body
        # (EPUB split-file title pages) never ranks as a start candidate, so
        # prepend preceding items while the ratio improves.
        j = start - 1
        while j >= 0:
            cand = source_words[source_ids[j]] + acc
            r2 = _ratio(cand, chapter_words)
            if r2 > r + 1e-9:
                r, acc = r2, cand
                span.insert(0, j)
                j -= 1
            else:
                break
        if r > best_r:
            best_r, best_span = r, span
    return best_r, best_span


def _paragraphs(text: str) -> List[str]:
    return [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]


def _apply_pipeline_hygiene(text: str, header_prefix: Optional[str],
                            strip_markers: bool) -> str:
    """Apply the same deterministic hygiene the EPUB pipeline applies
    (repeated page-header paragraphs, inline [N] endnote markers) to a
    source item, so fidelity compares like with like."""
    if strip_markers:
        from ..extract.epub import strip_endnote_markers
        text = strip_endnote_markers(text)
    if header_prefix:
        paragraphs = re.split(r"\n{2,}", text)
        kept = [p for p in paragraphs if not p.strip().startswith(header_prefix)]
        text = "\n\n".join(kept)
    return text


def compare_chapters(source_texts: Dict[str, str],
                     workdir_texts: Dict[str, str],
                     header_prefix: Optional[str] = None,
                     strip_markers: bool = False) -> FidelityReport:
    """Compare source items against workdir chapter texts.

    - per-chapter similarity (difflib ratio over normalized words)
    - dropped paragraphs: source paragraphs (≥ MIN_DROP_PARAGRAPH_WORDS
      words) from a chapter's matched span absent from the *entire* output
    - order anomalies: chapters whose matched source span starts before the
      previous chapter's span (out of spine/page sequence)
    - unmatched source items (usually deliberately excluded front/backmatter)

    `header_prefix` / `strip_markers` mirror the EPUB pipeline's narration
    hygiene (read from the workdir manifest QA by `run_fidelity_check`).
    """
    if header_prefix or strip_markers:
        source_texts = {
            sid: _apply_pipeline_hygiene(t, header_prefix, strip_markers)
            for sid, t in source_texts.items()}
    report = FidelityReport()
    source_ids = [sid for sid, t in source_texts.items() if t.strip()]
    source_words = {sid: _norm_words(source_texts[sid]) for sid in source_ids}

    if not workdir_texts:
        report.unmatched_source = list(source_ids)
        return report

    # Whole-output haystack for dropped-paragraph substring checks
    all_output = " ".join(
        " ".join(_norm_words(t)) for t in workdir_texts.values())

    matched_indices = set()
    prev_start = -1
    for chapter_id, chapter_text in workdir_texts.items():
        ch_words = _norm_words(chapter_text)
        similarity, span = _best_span(source_ids, source_words, ch_words)
        matched_indices.update(span)

        # Dropped paragraphs: from this chapter's matched source span
        dropped = []
        for idx in span:
            for para in _paragraphs(source_texts[source_ids[idx]]):
                words = _norm_words(para)
                if len(words) < MIN_DROP_PARAGRAPH_WORDS:
                    continue
                if " ".join(words) not in all_output:
                    dropped.append(para)

        if span and prev_start >= 0 and span[0] < prev_start:
            report.order_anomalies.append(
                f"{chapter_id}: source span starts at item {span[0] + 1} "
                f"before previous chapter's start (item {prev_start + 1})")
        if span:
            prev_start = span[0]

        report.chapters.append(ChapterFidelity(
            chapter=chapter_id,
            similarity=round(similarity, 4),
            matched_source=[source_ids[i] for i in span],
            dropped_paragraphs=dropped,
        ))

    report.unmatched_source = [
        sid for i, sid in enumerate(source_ids) if i not in matched_indices]
    return report


# ── report rendering ──────────────────────────────────────────────────────

def format_fidelity_report(report: FidelityReport,
                           source_label: str = "",
                           workdir_label: str = "") -> str:
    """Markdown table + anomaly sections + overall verdict."""
    lines = ["# Fidelity report", ""]
    if source_label or workdir_label:
        lines += [f"Source: `{source_label}`  •  Workdir: `{workdir_label}`", ""]

    if not report.chapters:
        lines += ["**No chapter texts found in the workdir** — run "
                  "`vorpal build <src> --stop-after segment` first.", "",
                  f"**Overall: {report.status.upper()}**", ""]
        return "\n".join(lines)

    lines += ["| Chapter | Similarity | Dropped ¶ | Source items | Status |",
              "|---|---|---|---|---|"]
    for ch in report.chapters:
        src = f"{len(ch.matched_source)}"
        lines.append(f"| {ch.chapter} | {ch.similarity:.3f} | "
                     f"{len(ch.dropped_paragraphs)} | {src} | {ch.status} |")
    lines.append("")

    if report.total_dropped:
        lines.append("## Dropped paragraphs")
        for ch in report.chapters:
            for para in ch.dropped_paragraphs:
                excerpt = para if len(para) <= 160 else para[:157] + "…"
                lines.append(f"- **{ch.chapter}**: {excerpt}")
        lines.append("")

    if report.order_anomalies:
        lines.append("## Order anomalies")
        for a in report.order_anomalies:
            lines.append(f"- {a}")
        lines.append("")

    if report.unmatched_source:
        lines.append("## Source items not matched to any chapter")
        lines.append("*(usually deliberately excluded front/backmatter — "
                     "verify nothing narrable is here)*")
        for sid in report.unmatched_source:
            lines.append(f"- {sid}")
        lines.append("")

    lines.append(f"**Overall: {report.status.upper()}** "
                 f"({len(report.chapters)} chapters, "
                 f"{report.total_dropped} dropped paragraph(s))")
    lines.append("")
    return "\n".join(lines)


def run_fidelity_check(source_path: Path, work_dir: Path) -> FidelityReport:
    """Convenience wrapper: extract both sides and compare.

    Reads the workdir manifest's QA to mirror the pipeline's EPUB narration
    hygiene (header pattern, endnote markers) on the source side.  Workdirs
    built before that hygiene existed have neither QA field and compare raw.
    """
    import json

    source_path, work_dir = Path(source_path), Path(work_dir)
    source_texts = extract_source_texts(source_path)
    workdir_texts = extract_workdir_chapter_texts(work_dir)

    header_prefix, strip_markers = None, False
    book_json = work_dir / "book.json"
    if book_json.exists():
        try:
            qa = json.loads(book_json.read_text(encoding="utf-8")).get("qa", {})
        except (ValueError, OSError):
            qa = {}
        header_prefix = qa.get("epub_header_pattern") or None
        strip_markers = qa.get("endnote_markers_stripped") is not None

    return compare_chapters(source_texts, workdir_texts,
                            header_prefix=header_prefix,
                            strip_markers=strip_markers)
