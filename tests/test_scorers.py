from inspect_ai.scorer import CORRECT, INCORRECT, NOANSWER

from sca_eval.scorers import verdict_score_value


def test_correct_when_prediction_matches_expected():
    assert verdict_score_value("vulnerable", "vulnerable") == CORRECT
    assert verdict_score_value("safe", "safe") == CORRECT


def test_incorrect_when_prediction_is_wrong_label():
    assert verdict_score_value("safe", "vulnerable") == INCORRECT
    assert verdict_score_value("vulnerable", "safe") == INCORRECT


def test_unknown_is_noanswer_not_incorrect():
    assert verdict_score_value("unknown", "vulnerable") == NOANSWER
    assert verdict_score_value("unknown", "safe") == NOANSWER
    assert NOANSWER != INCORRECT
