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
