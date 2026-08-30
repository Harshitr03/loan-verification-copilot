from loan_rules import load_rules, validate_dataset
from tests.loan_rules.helpers import make_clean_dataset


def test_clean_dataset_has_no_violations():
    assert validate_dataset(make_clean_dataset(), load_rules(None)) == []
