from sca_eval.datasets import load_dataset, DATASETS


def test_all_declared_datasets_load_and_are_nonempty():
    for name in DATASETS:
        samples = load_dataset(name)
        assert len(samples) >= 3, f"{name} should have >=3 seed samples"
        for s in samples:
            assert s.id, f"{name} sample missing id"
            assert isinstance(s.input, str) and s.input.strip()
            assert s.target, f"{name} sample {s.id} missing target"


def test_security_targets_are_valid_labels():
    for name in ("security_reasoning", "security_reasoning_hard"):
        for s in load_dataset(name):
            assert s.target in ("vulnerable", "safe"), f"{name}/{s.id}"


def test_unknown_dataset_raises():
    import pytest

    with pytest.raises(KeyError):
        load_dataset("does_not_exist")


def test_malformed_json_line_reports_file_and_line(tmp_path):
    import pytest

    from sca_eval.datasets import _load_jsonl

    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"id": "ok", "input": "x", "target": "y"}\nnot json\n')
    with pytest.raises(ValueError, match="line 2"):
        _load_jsonl(bad)


def test_missing_required_key_reports_context(tmp_path):
    import pytest

    from sca_eval.datasets import _load_jsonl

    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"id": "ok", "input": "x"}\n')  # no target
    with pytest.raises(ValueError, match="target"):
        _load_jsonl(bad)
