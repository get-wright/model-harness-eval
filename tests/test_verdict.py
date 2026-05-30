from sca_eval.verdict import parse_verdict


def test_parses_explicit_verdict_line():
    assert parse_verdict("Reasoning...\nVERDICT: VULNERABLE") == "vulnerable"
    assert parse_verdict("VERDICT: SAFE") == "safe"


def test_verdict_line_is_case_insensitive():
    assert parse_verdict("verdict: vulnerable") == "vulnerable"


def test_negation_prose_is_not_misread():
    # The whole point: no substring fallback.
    assert parse_verdict("This code is not vulnerable at all.") == "unknown"
    assert parse_verdict("I think this is vulnerable to injection.") == "unknown"


def test_uses_last_verdict_line_when_several():
    assert parse_verdict("VERDICT: SAFE\n...rethinking...\nVERDICT: VULNERABLE") == "vulnerable"


def test_returns_unknown_when_no_verdict_line():
    assert parse_verdict("I am not sure about this code.") == "unknown"


def test_mid_sentence_verdict_word_is_not_matched():
    # Must start a line; inline prose mentioning "verdict:" does not count.
    assert parse_verdict("The verdict: vulnerable code should be patched.") == "unknown"


def test_handles_crlf_line_endings():
    assert parse_verdict("Reasoning\r\nVERDICT: SAFE\r\n") == "safe"


def test_empty_string_is_unknown():
    assert parse_verdict("") == "unknown"


def test_trailing_text_after_label_is_tolerated():
    assert parse_verdict("VERDICT: VULNERABLE (SQL injection)") == "vulnerable"
