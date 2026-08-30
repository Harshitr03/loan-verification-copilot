import csv
import hashlib
from collections import Counter
import pytest
from loan_rules import load_rules, validate_dataset, write_default_rules_json
from data.generate import build_package, generate

REPRO = ["loan_tape.csv", "servicer_update.csv", "document_manifest.csv",
         "validation_rules.json", "expected_exception_sample.csv", "ground_truth_exceptions.csv"]


def _hash(d):
    h = hashlib.sha256()
    for name in REPRO:
        h.update((d / name).read_bytes())
    return h.hexdigest()


def test_reproducible_excluding_users_json(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    generate(str(a), rows=800, seed=42); generate(str(b), rows=800, seed=42)
    assert _hash(a) == _hash(b)


@pytest.mark.parametrize("seed", [1, 7, 42, 100, 2024])   # composition must hold on every seed
def test_superset_oracle_in_memory(tmp_path, seed):
    rules_path = tmp_path / "validation_rules.json"
    write_default_rules_json(str(rules_path))
    rules = load_rules(str(rules_path))
    ds, bundles = build_package(rules, rows=800, defect_rate=0.10, seed=seed)
    ground_pairs = {(b.row_uid, b.rule_id) for b in bundles}
    found = validate_dataset(ds, rules)
    found_pairs = {(v.row_uid, v.rule_id) for v in found}
    assert ground_pairs <= found_pairs, f"missing: {ground_pairs - found_pairs}"
    ground_uids = {b.row_uid for b in bundles}
    assert {v.row_uid for v in found} <= ground_uids, "a clean loan was flagged"


def test_every_type_meets_target(tmp_path):
    out = tmp_path / "o"; out.mkdir()
    generate(str(out), rows=5000, seed=42)
    c = Counter()
    with open(out / "ground_truth_exceptions.csv") as f:
        for row in csv.DictReader(f):
            c[row["rule_id"]] += 1
    for r in load_rules(None):
        assert c[r.id] >= 30, f"{r.id}={c[r.id]}"
