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
    for s in load_dataset("security_reasoning"):
        assert s.target in ("vulnerable", "safe")


def test_unknown_dataset_raises():
    import pytest

    with pytest.raises(KeyError):
        load_dataset("does_not_exist")
