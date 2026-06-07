"""Shared page/block data model and pages.jsonl serialization.

Both extraction paths (digital text layer, scanned OCR) emit Pages of Blocks
with geometry, so downstream segmentation can reason about layout and every
piece of text keeps its page provenance.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Block:
    bbox: tuple          # (x0, y0, x1, y1) in page coordinates (points or px)
    text: str
    font_size: float = None   # digital path only
    conf: float = 1.0          # 0..1; OCR confidence (digital text layer = 1.0)

    def to_dict(self) -> dict:
        d = {"bbox": list(self.bbox), "text": self.text, "conf": round(self.conf, 4)}
        if self.font_size is not None:
            d["font_size"] = round(self.font_size, 2)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Block":
        return cls(bbox=tuple(d["bbox"]), text=d["text"],
                   font_size=d.get("font_size"), conf=d.get("conf", 1.0))


@dataclass
class Page:
    index: int           # 0-based PDF page index
    kind: str            # "digital" | "scanned" | "empty"
    width: float
    height: float
    blocks: list = field(default_factory=list)
    conf: float = 1.0    # mean OCR confidence 0..1
    quality: float = 0.0  # text_quality of page text
    score: float = 0.0    # conf x quality
    flagged: bool = False
    note: str = ""        # e.g. which OCR attempt won, why flagged

    @property
    def text(self) -> str:
        return "\n".join(b.text for b in self.blocks if b.text.strip())

    def to_dict(self) -> dict:
        return {
            "index": self.index, "kind": self.kind,
            "width": round(self.width, 2), "height": round(self.height, 2),
            "conf": round(self.conf, 4), "quality": round(self.quality, 4),
            "score": round(self.score, 4),
            "flagged": self.flagged, "note": self.note,
            "blocks": [b.to_dict() for b in self.blocks],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Page":
        return cls(
            index=d["index"], kind=d["kind"],
            width=d["width"], height=d["height"],
            blocks=[Block.from_dict(b) for b in d.get("blocks", [])],
            conf=d.get("conf", 1.0), quality=d.get("quality", 0.0),
            score=d.get("score", 0.0),
            flagged=d.get("flagged", False), note=d.get("note", ""),
        )


def write_pages_jsonl(pages: list, path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for page in pages:
            f.write(json.dumps(page.to_dict(), ensure_ascii=False) + "\n")


def read_pages_jsonl(path: Path) -> list:
    pages = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                pages.append(Page.from_dict(json.loads(line)))
    return pages
