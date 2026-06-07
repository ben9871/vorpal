from vorpal.extract.quality import (
    function_word_rate,
    page_score,
    text_quality,
    wordlike_ratio,
)

PROSE = (
    "Socialist thinkers prior to Marx and Engels had been able to do no more "
    "than moralize about existing social inequalities, positing an ideal world "
    "where class privilege and exploitation should not exist."
)

# Real titles from the v0 Firestone chapters.json — OCR'd diagram garbage
GARBAGE = "ROUVOINWHOD TSAR LHVLSHI MCE AM CE CIVILI BRROCICAL DIVISION SPECS"


def test_prose_scores_high():
    assert text_quality(PROSE) > 0.7


def test_ocr_garbage_scores_low():
    assert text_quality(GARBAGE) < 0.45


def test_prose_beats_garbage_decisively():
    assert text_quality(PROSE) > text_quality(GARBAGE) + 0.3


def test_empty_text_scores_zero():
    assert text_quality("") == 0.0
    assert wordlike_ratio("") == 0.0
    assert function_word_rate("123 456 !!!") == 0.0


def test_function_words_in_prose():
    assert function_word_rate(PROSE) > 0.25
    assert function_word_rate(GARBAGE) == 0.0


def test_page_score_scales_with_confidence():
    full = page_score(1.0, PROSE)
    half = page_score(0.5, PROSE)
    assert abs(half - full / 2) < 1e-9
