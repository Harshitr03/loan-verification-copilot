from loan_rules import load_rules, validate_dataset
from data._clean import build_clean_dataset


def test_clean_dataset_passes_every_rule():
    ds = build_clean_dataset(n=300, seed=7)
    v = validate_dataset(ds, load_rules(None))
    assert v == [], f"clean tripped: {[x.rule_id for x in v][:5]}"


def test_clean_dataset_reproducible():
    a, b = build_clean_dataset(50, 1), build_clean_dataset(50, 1)
    assert [l["interest_rate"] for l in a.loans] == [l["interest_rate"] for l in b.loans]
    assert [l["row_uid"] for l in a.loans] == [l["row_uid"] for l in b.loans]
