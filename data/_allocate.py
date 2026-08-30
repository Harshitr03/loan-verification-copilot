from __future__ import annotations
from math import ceil


def plan_row_defects(row_rule_ids, eligible_indices, rng, n_loans,
                     per_type=35, defect_rate=0.10, max_per_row=2):
    flat = [rid for rid in row_rule_ids for _ in range(per_type)]
    rng.shuffle(flat)

    budget = round(defect_rate * n_loans)
    needed = ceil(len(flat) / max_per_row)
    n_rows = min(len(eligible_indices), max(budget, needed))

    chosen = [int(x) for x in rng.choice(eligible_indices, size=n_rows, replace=False)]
    assign = {i: [] for i in chosen}
    # round-robin: one pass across all rows, then a second pass -> spread, cap respected
    slots = chosen * max_per_row
    for rid, slot in zip(flat, slots):
        assign[slot].append(rid)
    return {k: v for k, v in assign.items() if v}
