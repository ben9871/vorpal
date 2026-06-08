"""Export: render a manifest + chapter bodies to alternative text formats.

Usage:
    vorpal export book.pdf --as txt
    vorpal export book.epub --as epub --output my_clean_book.epub

The manifest (book.json) produced by ``vorpal build`` is the real asset;
the audiobook is one renderer of many. This module provides the others:

  txt   — one plain-text file per chapter, joined in reading order,
          with chapter headings. Footnotes appended as a separate section.
  epub  — minimal valid EPUB 3: OPF package, nav.xhtml, per-chapter XHTML.
          No CSS, no cover image — the point is structural correctness.
"""

import re
import zipfile
from pathlib import Path


# ── body retrieval ────────────────────────────────────────────────────────────


def get_chapter_body(section, work_dir: Path, safe_filename_fn) -> str:
    """Return the body text for a section.

    EPUB/TXT sources: body is stored inline on the section (section.body).
    PDF sources: body was written to chapter_texts/ during the build; read it
    from there so we don't need to reload pages_segmented.jsonl.
    """
    if section.body:
        return section.body
    ct_dir = work_dir / "chapter_texts"
    fname = f"{section.id:02d}_{safe_filename_fn(section.title)}.txt"
    p = ct_dir / fname
    if p.exists():
        return p.read_text(encoding="utf-8")
    return ""


def load_footnotes(work_dir: Path) -> list:
    """Load the footnote list from the manifest workdir (may be empty)."""
    import json
    fp = work_dir / "footnotes.json"
    if not fp.exists():
        return []
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (ValueError, OSError):
        return []


# ── TXT renderer ──────────────────────────────────────────────────────────────


def export_txt(sections, work_dir: Path, output_path: Path, safe_filename_fn) -> Path:
    """Write a structured plain-text export.

    Format:
        # Chapter Title

        Body text…


        ## Footnotes (if present)

        [1] Footnote text…
    """
    parts = []
    for section in sections:
        if not section.include:
            continue
        body = get_chapter_body(section, work_dir, safe_filename_fn)
        if not body.strip():
            continue
        parts.append(f"# {section.title}\n\n{body.strip()}")

    footnotes = load_footnotes(work_dir)
    if footnotes:
        fn_lines = [f"[{i + 1}] {fn}" for i, fn in enumerate(footnotes)]
        parts.append("## Footnotes\n\n" + "\n\n".join(fn_lines))

    output_path.write_text("\n\n\n".join(parts) + "\n", encoding="utf-8")
    return output_path


# ── EPUB renderer ─────────────────────────────────────────────────────────────


def export_epub(sections, work_dir: Path, output_path: Path,
                title: str, author: str, safe_filename_fn) -> Path:
    """Write a minimal valid EPUB 3.

    Structure:
        mimetype                       (uncompressed, first)
        META-INF/container.xml
        OEBPS/package.opf
        OEBPS/nav.xhtml
        OEBPS/chapter_NNN.xhtml       (one per included section)
    """
    chapters = []
    for section in sections:
        if not section.include:
            continue
        body = get_chapter_body(section, work_dir, safe_filename_fn)
        if not body.strip():
            continue
        chapters.append({
            "id": section.id,
            "title": section.title,
            "body": body.strip(),
            "filename": f"chapter_{len(chapters) + 1:03d}.xhtml",
        })

    with zipfile.ZipFile(str(output_path), "w", zipfile.ZIP_DEFLATED) as zf:
        # mimetype must be first and stored uncompressed (EPUB spec §3.3)
        mi = zipfile.ZipInfo("mimetype")
        mi.compress_type = zipfile.ZIP_STORED
        zf.writestr(mi, "application/epub+zip")

        zf.writestr("META-INF/container.xml", _container_xml())
        zf.writestr("OEBPS/package.opf", _package_opf(title, author, chapters))
        zf.writestr("OEBPS/nav.xhtml", _nav_xhtml(title, chapters))

        for ch in chapters:
            zf.writestr(f"OEBPS/{ch['filename']}",
                        _chapter_xhtml(ch["title"], ch["body"]))

    return output_path


# ── EPUB fragment builders ────────────────────────────────────────────────────


def _xml_escape(text: str) -> str:
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def _container_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<container version="1.0" '
        'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
        '  <rootfiles>\n'
        '    <rootfile full-path="OEBPS/package.opf"'
        ' media-type="application/oebps-package+xml"/>\n'
        '  </rootfiles>\n'
        '</container>'
    )


def _package_opf(title: str, author: str, chapters: list) -> str:
    manifest_items = "\n    ".join(
        f'<item id="ch{i + 1}" href="{ch["filename"]}"'
        f' media-type="application/xhtml+xml"/>'
        for i, ch in enumerate(chapters)
    )
    if manifest_items:
        manifest_items += "\n    "
    manifest_items += (
        '<item id="nav" href="nav.xhtml"'
        ' media-type="application/xhtml+xml" properties="nav"/>'
    )
    spine_items = "\n    ".join(
        f'<itemref idref="ch{i + 1}"/>'
        for i in range(len(chapters))
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0"'
        ' unique-identifier="bookid">\n'
        '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        f'    <dc:title>{_xml_escape(title)}</dc:title>\n'
        f'    <dc:creator>{_xml_escape(author)}</dc:creator>\n'
        '    <dc:language>en</dc:language>\n'
        '    <dc:identifier id="bookid">vorpal-export</dc:identifier>\n'
        '  </metadata>\n'
        '  <manifest>\n'
        f'    {manifest_items}\n'
        '  </manifest>\n'
        '  <spine>\n'
        f'    {spine_items}\n'
        '  </spine>\n'
        '</package>'
    )


def _nav_xhtml(title: str, chapters: list) -> str:
    nav_items = "\n      ".join(
        f'<li><a href="{ch["filename"]}">{_xml_escape(ch["title"])}</a></li>'
        for ch in chapters
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE html>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml"'
        ' xmlns:epub="http://www.idpf.org/2007/ops">\n'
        f'<head><title>{_xml_escape(title)}</title></head>\n'
        '<body>\n'
        '  <nav epub:type="toc">\n'
        '    <h1>Contents</h1>\n'
        '    <ol>\n'
        f'      {nav_items}\n'
        '    </ol>\n'
        '  </nav>\n'
        '</body>\n'
        '</html>'
    )


def _chapter_xhtml(title: str, body: str) -> str:
    paragraphs = "\n  ".join(
        f"<p>{_xml_escape(para.strip())}</p>"
        for para in re.split(r"\n\n+", body)
        if para.strip()
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE html>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml">\n'
        f'<head><title>{_xml_escape(title)}</title></head>\n'
        '<body>\n'
        f'  <h1>{_xml_escape(title)}</h1>\n'
        f'  {paragraphs}\n'
        '</body>\n'
        '</html>'
    )
