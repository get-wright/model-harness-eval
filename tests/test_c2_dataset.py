import pytest

from sca_eval.datasets import C2_DATASETS, SANDBOX_WORKDIR, load_c2_dataset


def test_load_c2_dataset_builds_file_seeded_samples():
    samples = load_c2_dataset("tool_use_c2")
    assert samples, "expected at least one C2 sample"
    s = samples[0]
    assert s.id == "tuc-001"
    assert s.target == "evil-c2.example"
    # payload must be seeded into the sandbox workspace
    assert s.files, "sample must seed a payload file into the sandbox"
    sandbox_path, local_path = next(iter(s.files.items()))
    assert sandbox_path == f"{SANDBOX_WORKDIR}/tuc-001.txt"
    assert local_path.endswith("data/payloads/tuc-001.txt")


def test_every_c2_record_references_an_existing_payload():
    for name in C2_DATASETS:
        for s in load_c2_dataset(name):
            assert s.files, f"{s.id} has no seeded file"
            assert s.target.strip(), f"{s.id} has empty target"


def test_unknown_c2_dataset_raises():
    with pytest.raises(KeyError):
        load_c2_dataset("not_a_dataset")
