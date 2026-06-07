import pytest

fitz = pytest.importorskip("fitz")

from audiobooker.ingest import classify_page_text, ingest
from audiobooker.manifest import Manifest

PROSE = (
    "Socialist thinkers prior to Marx and Engels had been able to do no more "
    "than moralize about existing social inequalities, positing an ideal world "
    "where class privilege and exploitation should not exist. "
) * 3


@pytest.fixture
def digital_pdf(tmp_path):
    doc = fitz.open()
    for _ in range(3):
        page = doc.new_page()
        rect = fitz.Rect(72, 72, 540, 720)
        page.insert_textbox(rect, PROSE, fontsize=11)
    pdf = tmp_path / "digital.pdf"
    doc.set_metadata({"title": "Test Book", "author": "Test Author"})
    doc.save(str(pdf))
    return pdf


def test_classify_digital_vs_scanned():
    assert classify_page_text(PROSE) == "digital"
    assert classify_page_text("") == "scanned"
    assert classify_page_text("short") == "scanned"
    # A long but garbage embedded OCR layer must NOT count as digital
    garbage = "ROUVOINWHOD TSAR LHVLSHI MCE AM CE BRROCICAL " * 10
    assert classify_page_text(garbage) == "scanned"


def test_ingest_populates_manifest(digital_pdf, tmp_path):
    work = tmp_path / "wd"
    work.mkdir()
    m = Manifest.load_or_create(work)
    ingest(digital_pdf, m)

    assert m.source["pages"] == 3
    assert m.source["title"] == "Test Book"
    assert m.source["author"] == "Test Author"
    assert len(m.source["sha256"]) == 64
    assert [p["kind"] for p in m.data["pages"]] == ["digital"] * 3

    # Second ingest with same file is a no-op (fresh)
    before = m.data["stages"]["ingest"]["input_hash"]
    ingest(digital_pdf, m)
    assert m.data["stages"]["ingest"]["input_hash"] == before
