import numpy as np
from collections import Counter
from math import ceil
from data._allocate import plan_row_defects

ROW_IDS = ["required_fields", "valid_dates", "maturity_after_origination",
           "non_negative_amounts", "balance_le_principal", "interest_rate_range",
           "payment_status_vs_dpd", "closed_with_balance", "valid_state_code", "stale_record"]


def test_each_row_type_hits_target():
    assign = plan_row_defects(ROW_IDS, list(range(5000)), np.random.default_rng(0),
                              n_loans=5000, per_type=35)
    c = Counter(rid for rids in assign.values() for rid in rids)
    for rid in ROW_IDS:
        assert c[rid] >= 35, f"{rid}={c[rid]}"


def test_respects_cap_and_spreads():
    assign = plan_row_defects(ROW_IDS, list(range(5000)), np.random.default_rng(0),
                              n_loans=5000, per_type=35, defect_rate=0.10)
    assert all(len(v) <= 2 for v in assign.values())
    # 350 assignments spread one-per-row first -> ~350 defective rows, not ~175
    assert len(assign) >= 300


def test_only_uses_eligible_indices():
    eligible = list(range(100, 200))
    assign = plan_row_defects(ROW_IDS, eligible, np.random.default_rng(0),
                              n_loans=5000, per_type=5)
    assert set(assign).issubset(set(eligible))
