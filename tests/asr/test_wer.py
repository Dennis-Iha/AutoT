from core.asr.wer import character_error_rate, edit_distance, normalize_text, word_error_rate


def test_edit_distance_identical():
    assert edit_distance(["a", "b", "c"], ["a", "b", "c"]) == 0


def test_edit_distance_substitution():
    assert edit_distance(["a", "b", "c"], ["a", "x", "c"]) == 1


def test_edit_distance_insertion_deletion():
    assert edit_distance(["a", "b"], ["a", "b", "c"]) == 1
    assert edit_distance(["a", "b", "c"], ["a", "b"]) == 1


def test_normalize_text_strips_punctuation_and_case():
    assert normalize_text("Where is the train station?") == "where is the train station"


def test_normalize_text_collapses_whitespace():
    assert normalize_text("  hello   world  ") == "hello world"


def test_wer_perfect_match_is_zero():
    assert word_error_rate("hello world", "hello world") == 0.0


def test_wer_one_substitution_out_of_two_words():
    assert word_error_rate("hello world", "hello there") == 0.5


def test_wer_ignores_case_and_punctuation():
    assert word_error_rate("Hello, World!", "hello world") == 0.0


def test_wer_empty_reference_and_hypothesis():
    assert word_error_rate("", "") == 0.0


def test_wer_empty_reference_nonempty_hypothesis():
    assert word_error_rate("", "hello") == 1.0


def test_cer_perfect_match_is_zero():
    assert character_error_rate("hello", "hello") == 0.0


def test_cer_one_char_diff():
    assert character_error_rate("cat", "cot") == 1 / 3
