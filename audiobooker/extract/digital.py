"""Digital extraction: pull the embedded text layer as layout blocks.

Uses PyMuPDF's dict extraction so every block keeps its bounding box and
dominant font size — segmentation needs both (header/footer bands, heading
font-size outliers).
"""

import statistics

from .pagemodel import Block, Page
from .quality import text_quality


def extract_digital_page(doc, index: int) -> Page:
    """Extract one page's text layer as Blocks. doc is an open fitz.Document."""
    page = doc[index]
    raw = page.get_text("dict")

    blocks = []
    for raw_block in raw.get("blocks", []):
        if raw_block.get("type") != 0:  # 0 = text block; skip images
            continue
        lines = []
        sizes = []
        for line in raw_block.get("lines", []):
            spans = line.get("spans", [])
            line_text = "".join(s.get("text", "") for s in spans)
            if line_text.strip():
                lines.append(line_text)
                sizes.extend(s.get("size", 0) for s in spans if s.get("text", "").strip())
        if not lines:
            continue
        blocks.append(Block(
            bbox=tuple(raw_block["bbox"]),
            text="\n".join(lines),
            font_size=statistics.median(sizes) if sizes else None,
            conf=1.0,
        ))

    text = "\n".join(b.text for b in blocks)
    quality = text_quality(text)
    return Page(
        index=index, kind="digital",
        width=page.rect.width, height=page.rect.height,
        blocks=blocks,
        conf=1.0, quality=quality, score=quality,
        flagged=False,
    )
