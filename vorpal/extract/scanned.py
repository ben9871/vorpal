"""Scanned extraction v2: preprocess page images, OCR to layout blocks.

Replaces the v0 raw-rasterize-and-dump approach (docs/01-audit.md §1):

  render gray @ DPI → despeckle → deskew → binarize → strip border
  artifacts (binding shadows) → Tesseract TSV → blocks with per-word
  confidence → page QA score → retry ladder for weak pages

Every page gets a score = mean OCR confidence × text quality; pages that stay
weak after retries are flagged in the manifest for human review instead of
silently poisoning the book.
"""

import numpy as np

from .pagemodel import Block, Page
from .quality import page_score, text_quality
from ..binaries import require_tesseract

# QA thresholds (calibrated on the Firestone scan, the regression book)
RETRY_THRESHOLD = 0.70   # score below this → try the next OCR attempt
FLAG_THRESHOLD = 0.60    # best score below this → page flagged for review
BLANK_INK_RATIO = 0.005  # less ink than this → genuinely blank page

# OCR attempt ladder: (dpi multiplier, tesseract page-segmentation mode)
ATTEMPTS = [
    (1.0, 1),   # baseline: auto page segmentation with OSD
    (1.0, 3),   # plain auto segmentation (handles some layouts better)
    (1.5, 1),   # higher resolution rescue
]


# ─────────────────────────────────────────────
# Image preprocessing
# ─────────────────────────────────────────────

def render_page_gray(doc, index: int, dpi: int) -> np.ndarray:
    """Render one PDF page to a grayscale uint8 array."""
    import fitz
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = doc[index].get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)


def estimate_skew(binary: np.ndarray) -> float:
    """Estimate page skew in degrees from the dark-pixel cloud."""
    import cv2
    coords = np.column_stack(np.where(binary == 0))
    if len(coords) < 500:
        return 0.0
    angle = cv2.minAreaRect(coords[:, ::-1].astype(np.float32))[-1]
    if angle > 45:
        angle -= 90
    return float(angle)


def deskew(gray: np.ndarray, binary: np.ndarray) -> np.ndarray:
    """Rotate the grayscale image to correct small skews (0.2°–5°)."""
    import cv2
    angle = estimate_skew(binary)
    if abs(angle) < 0.2 or abs(angle) > 5.0:
        return gray
    h, w = gray.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(gray, m, (w, h), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=255)


def strip_border_artifacts(binary: np.ndarray) -> np.ndarray:
    """Whiten large dark components touching the page border — binding
    shadows and scan edges, the source of v0's stray '|' margin noise."""
    import cv2
    h, w = binary.shape
    inverted = (binary == 0).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(inverted, connectivity=8)
    cleaned = binary.copy()
    for i in range(1, n):
        x, y, bw, bh, _area = stats[i]
        touches_border = x == 0 or y == 0 or x + bw >= w or y + bh >= h
        is_large_bar = bh > 0.5 * h or bw > 0.5 * w
        if touches_border and is_large_bar:
            cleaned[labels == i] = 255
    return cleaned


def preprocess(gray: np.ndarray) -> np.ndarray:
    """Full preprocessing chain: despeckle → deskew → binarize → de-border."""
    import cv2
    gray = cv2.medianBlur(gray, 3)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    gray = deskew(gray, binary)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return strip_border_artifacts(binary)


def ink_ratio(binary: np.ndarray) -> float:
    return float((binary == 0).mean())


# ─────────────────────────────────────────────
# OCR to blocks
# ─────────────────────────────────────────────

def ocr_to_blocks(binary: np.ndarray, psm: int) -> tuple:
    """Run Tesseract TSV on a preprocessed image.

    Returns (blocks, mean_confidence 0..1). Words are grouped into
    (block, paragraph) units with line structure preserved inside each block.
    """
    import pytesseract
    from PIL import Image

    pytesseract.pytesseract.tesseract_cmd = require_tesseract()

    data = pytesseract.image_to_data(
        Image.fromarray(binary), lang="eng",
        config=f"--psm {psm} --oem 3",
        output_type=pytesseract.Output.DICT,
    )

    groups = {}  # (block_num, par_num) -> {lines: {line_num: [words]}, boxes, confs}
    confs = []
    n = len(data["text"])
    for i in range(n):
        word = data["text"][i].strip()
        if not word:
            continue
        conf = float(data["conf"][i])
        if conf < 0:
            continue
        key = (data["block_num"][i], data["par_num"][i])
        g = groups.setdefault(key, {"lines": {}, "boxes": [], "confs": []})
        g["lines"].setdefault(data["line_num"][i], []).append(word)
        g["boxes"].append((data["left"][i], data["top"][i],
                           data["left"][i] + data["width"][i],
                           data["top"][i] + data["height"][i]))
        g["confs"].append(conf)
        confs.append(conf)

    blocks = []
    for key in sorted(groups):
        g = groups[key]
        text = "\n".join(" ".join(g["lines"][ln]) for ln in sorted(g["lines"]))
        xs0, ys0, xs1, ys1 = zip(*g["boxes"])
        blocks.append(Block(
            bbox=(min(xs0), min(ys0), max(xs1), max(ys1)),
            text=text,
            conf=sum(g["confs"]) / len(g["confs"]) / 100.0,
        ))

    mean_conf = (sum(confs) / len(confs) / 100.0) if confs else 0.0
    return blocks, mean_conf


# ─────────────────────────────────────────────
# Page extraction with retry ladder
# ─────────────────────────────────────────────

def extract_scanned_page(doc, index: int, dpi: int = 300) -> Page:
    """OCR one page, retrying weak results at alternate settings, and score it."""
    page_rect = doc[index].rect

    best = None  # (score, blocks, conf, quality, note)
    for dpi_mult, psm in ATTEMPTS:
        attempt_dpi = int(dpi * dpi_mult)
        gray = render_page_gray(doc, index, attempt_dpi)
        binary = preprocess(gray)

        if ink_ratio(binary) < BLANK_INK_RATIO:
            return Page(index=index, kind="scanned",
                        width=page_rect.width, height=page_rect.height,
                        blocks=[], conf=1.0, quality=0.0, score=0.0,
                        flagged=False, note="blank page")

        blocks, conf = ocr_to_blocks(binary, psm)
        # Scale pixel bboxes back to PDF points so digital and scanned pages
        # share one coordinate system (Phase 2 layout logic relies on it).
        scale = 72.0 / attempt_dpi
        for b in blocks:
            b.bbox = tuple(round(v * scale, 2) for v in b.bbox)
        text = "\n".join(b.text for b in blocks)
        quality = text_quality(text)
        score = page_score(conf, text)
        note = f"dpi={attempt_dpi} psm={psm}"

        if best is None or score > best[0]:
            best = (score, blocks, conf, quality, note)
        if best[0] >= RETRY_THRESHOLD:
            break  # good enough — no more attempts

    score, blocks, conf, quality, note = best
    flagged = score < FLAG_THRESHOLD
    if flagged:
        note += " (low quality after retries)"
    return Page(index=index, kind="scanned",
                width=page_rect.width, height=page_rect.height,
                blocks=blocks, conf=conf, quality=quality, score=score,
                flagged=flagged, note=note)
