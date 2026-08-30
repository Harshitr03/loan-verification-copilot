from __future__ import annotations
import argparse
import os
import numpy as np
from loan_rules import load_rules, write_default_rules_json
from loan_rules.base import Scope
from loan_rules.rules_row import ROW_FOOTPRINTS
from data._clean import build_clean_dataset
from data._allocate import plan_row_defects
from data._serialize import (write_loans_csv, write_rows_csv, write_ground_truth_csv,
                             write_sample_csv, write_users_json)

DATASET_ORDER = ["source_conflict", "document_status_present", "duplicate_borrower_combo",
                 "suspicious_borrower_repeat", "duplicate_loan_id"]   # id-mutating rules last
PER_TYPE_TARGET = 35

USERS = [
    {"username": "operator", "role": "data_operator", "display_name": "Data Operator", "password": "operator123"},
    {"username": "reviewer", "role": "reviewer", "display_name": "Reviewer", "password": "reviewer123"},
    {"username": "consumer", "role": "data_consumer", "display_name": "Data Consumer", "password": "consumer123"},
]


def _apply_dataset_rule(ds, rule, rng, target, avoid):
    """Corrupt until `target` distinct row_uids implicated; never re-touch an
    already-implicated loan (this kills the DATASET<->DATASET interference that
    otherwise dissolves earlier collisions or orphans cross-file joins)."""
    seen, bundles, attempts = set(), [], 0
    local_avoid = set(avoid)
    while len(seen) < target and attempts < target * 4 + 5:
        attempts += 1
        ds, bs = rule.corrupt(ds, rng, rule.params, avoid=local_avoid)
        for b in bs:
            local_avoid.add(b.row_uid)          # never reuse, even a duplicate touch
            if b.row_uid not in seen:
                seen.add(b.row_uid)
                bundles.append(b)
    return ds, bundles, seen


def build_package(rules, rows=5000, defect_rate=0.10, seed=1234):
    by_id = {r.id: r for r in rules}
    ds = build_clean_dataset(n=rows, seed=seed)
    initial_uids = {l["row_uid"] for l in ds.loans}

    root = np.random.default_rng(seed)
    subs = {r.id: s for r, s in zip(rules, root.spawn(len(rules)))}

    bundles, dataset_uids = [], set()
    for rid in DATASET_ORDER:
        rule = by_id.get(rid)
        if rule is None:            # disabled/filtered out
            continue
        ds, bs, seen = _apply_dataset_rule(ds, rule, subs[rid], PER_TYPE_TARGET,
                                           avoid=dataset_uids)
        bundles.extend(bs)
        dataset_uids |= seen                     # threaded into the next rule's `avoid`

    # ROW pool = original loans NOT implicated by any dataset rule
    eligible = [idx for idx, l in enumerate(ds.loans)
                if l["row_uid"] in initial_uids and l["row_uid"] not in dataset_uids]
    row_ids = [r.id for r in rules if r.scope == Scope.ROW]
    assign = plan_row_defects(row_ids, eligible, root, n_loans=rows,
                              per_type=35, defect_rate=defect_rate,
                              footprints=ROW_FOOTPRINTS)
    for idx, rule_ids in assign.items():
        for rid in dict.fromkeys(rule_ids):        # dedupe same rule on one row
            loan, b = by_id[rid].corrupt(ds.loans[idx], subs[rid], by_id[rid].params)
            ds.loans[idx] = loan
            bundles.append(b)

    # Repair manifest for ADDED cluster rows only (never re-add doc-removed originals)
    manifest_ids = {m["loan_id"] for m in ds.manifest}
    for l in ds.loans:
        if l["row_uid"] not in initial_uids and l["loan_id"] not in manifest_ids:
            ds.manifest.append({"loan_id": l["loan_id"], "document_status": l.get("document_status", "COMPLETE")})
            manifest_ids.add(l["loan_id"])

    return ds, bundles


def generate(out_dir, rows=5000, defect_rate=0.10, seed=1234):
    os.makedirs(out_dir, exist_ok=True)
    rules_path = os.path.join(out_dir, "validation_rules.json")
    write_default_rules_json(rules_path)
    rules = load_rules(rules_path)
    ds, bundles = build_package(rules, rows=rows, defect_rate=defect_rate, seed=seed)

    write_loans_csv(os.path.join(out_dir, "loan_tape.csv"), ds.loans)
    write_rows_csv(os.path.join(out_dir, "servicer_update.csv"), ds.servicer_updates,
                   ["loan_id", "current_balance", "interest_rate", "payment_status"])
    write_rows_csv(os.path.join(out_dir, "document_manifest.csv"), ds.manifest,
                   ["loan_id", "document_status"])
    write_ground_truth_csv(os.path.join(out_dir, "ground_truth_exceptions.csv"), bundles)
    _sample = _one_per_rule(bundles)
    write_sample_csv(os.path.join(out_dir, "expected_exception_sample.csv"), _sample)
    write_users_json(os.path.join(out_dir, "users.json"), USERS)
    return {"rows": len(ds.loans), "defects": len(bundles)}


def _one_per_rule(bundles, cap=25):
    seen, out = set(), []
    for b in sorted(bundles, key=lambda b: (b.rule_id, b.row_uid)):
        if b.rule_id not in seen:
            seen.add(b.rule_id)
            out.append(b)
    return out[:cap]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=5000)
    ap.add_argument("--defect-rate", type=float, default=0.10)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--out-dir", default="data")
    a = ap.parse_args()
    print(generate(a.out_dir, rows=a.rows, defect_rate=a.defect_rate, seed=a.seed))


if __name__ == "__main__":
    main()
