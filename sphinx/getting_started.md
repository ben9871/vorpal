# Getting Started

## Requirements

- **Python 3.10–3.12** (not 3.13 — the Kokoro TTS engine caps at 3.12)
- **ffmpeg** — audio encoding and M4B assembly
- **Tesseract OCR** — only needed for scanned PDF input
- **GPU recommended** — Kokoro synthesises at ~10–15× real-time on a mid-range NVIDIA GPU; CPU is ~0.3–0.5× (hours for a full novel)

### Installing system dependencies

**Windows:**
- ffmpeg: download from [gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/) and add `C:\ffmpeg\bin` to PATH
- Tesseract: [github.com/UB-Mannheim/tesseract/wiki](https://github.com/UB-Mannheim/tesseract/wiki)

**Linux / Debian:**
```bash
apt-get install -y tesseract-ocr ffmpeg espeak-ng
```

**Docker (recommended for autonomous/server use):**
```powershell
docker\run.ps1          # launches vorpal-box with everything pre-installed
```

## Installation

```bash
# Editable install (adds `vorpal` to PATH)
pip install -e .

# With LLM extras (tone tagging — Phase 8)
pip install -e ".[llm]"

# With API TTS extras (OpenAI engine)
pip install -e ".[api]"

# With audio analysis (ASR check, tone evaluation)
pip install -e ".[audio]"

# With local web UI
pip install -e ".[web]"

# Docs
pip install -e ".[docs]"
```

## GPU check

```bash
python -c "import torch; print(torch.cuda.is_available())"
```

If this prints `False` on a machine with an NVIDIA GPU, reinstall torch from the CUDA index:
```bash
pip install torch --index-url https://download.pytorch.org/whl/cu121
```

## Quick start

```bash
# EPUB → M4B (fastest path, no OCR)
vorpal build book.epub

# PDF → M4B (born-digital, text layer present)
vorpal build book.pdf

# Scanned PDF → M4B (triggers Tesseract OCR)
vorpal build scan.pdf --dpi 400

# Quick test slice (first 30 pages only)
vorpal build book.pdf --end-page 30 --output test

# Choose a voice
vorpal build book.epub --voice blend_deep_steady

# See all available voices
vorpal voices
```

## First audiobook — step by step

Download a public-domain EPUB from Project Gutenberg:

```bash
curl -o wells.epub "https://www.gutenberg.org/ebooks/35.epub.noimages"
vorpal build wells.epub --output time_machine
```

vorpal will:
1. Parse the EPUB spine and TOC — chapter boundaries are read directly from the file
2. Normalize the text (expand abbreviations and numbers, chunk at sentence/paragraph boundaries)
3. Synthesise each chunk with Kokoro (GPU if available)
4. Assemble a loudness-normalised `.m4b` with chapter markers

The output is `time_machine.m4b`. Copy it to your phone or import it into Apple Books.

## Building the Sphinx docs

```bash
cd sphinx
pip install -e ".[docs]"   # install sphinx + furo + myst-parser
make html                   # build to sphinx/_build/html/
open _build/html/index.html
```
