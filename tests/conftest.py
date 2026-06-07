from pathlib import Path

import pytest

ASSETS = Path(__file__).parent / "assets"


@pytest.fixture
def firestone_excerpt() -> Path:
    pdf = ASSETS / "firestone_excerpt_p15-24.pdf"
    if not pdf.exists():
        pytest.skip("firestone excerpt asset missing")
    return pdf
