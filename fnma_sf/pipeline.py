from __future__ import annotations
from loan_rules import load_rules, validate_dataset, Dataset
from fnma_sf.normalize import is_failed
from fnma_sf.panel import validate_panel
from fnma_sf.collapse import collapse_latest

# Rules whose required inputs the FNMA source structurally cannot supply, and which
# flag on ABSENCE (rather than skip) — so on this source they would flag every loan.
# Their absent fields (borrower_id; document_status/manifest) are surfaced instead by
# normalize_row's partial-import mechanism (§6.3). The rules stay UNCHANGED and strict
# on the graded synthetic tape; the connector just doesn't run them here — the same
# field-availability gating Pass 1 applies via `profiles`.
# (The borrower-counter rules already no-op: loan_rules null-guards them against a null
#  borrower_id; source_conflict no-ops with no servicer_update.)
FNMA_PASS3_SKIP = {"required_fields", "document_status_present"}


def pass3_rules():
    return [r for r in load_rules(None) if r.id not in FNMA_PASS3_SKIP]


def ingest_panel(rows: list[dict]) -> dict:
    failed = [r for r in rows if is_failed(r)]
    good = [r for r in rows if not is_failed(r)]
    panel = validate_panel(good)
    loan_tape = collapse_latest(good) if good else []
    loan_exceptions = validate_dataset(Dataset(loan_tape, [], []), pass3_rules()) if loan_tape else []
    return {"panel": panel, "loan_tape": loan_tape,
            "loan_exceptions": loan_exceptions, "failed": failed}


from fnma_sf.parse import iter_rows
from fnma_sf.normalize import normalize_row
from data._serialize import write_loans_csv


def _period_key(raw):
    p = raw["reporting_period"]
    return (int(p[2:]), int(p[:2])) if len(p) == 6 and p.isdigit() else (0, 0)


def build_demo_tape(src_path, out_csv, n_loans=5000) -> int:
    best: dict[str, dict] = {}
    for raw in iter_rows(src_path):              # single streaming pass, O(n_loans) memory
        lid = raw["loan_id"]
        if lid not in best:
            if len(best) >= n_loans:
                continue                         # only the first n_loans distinct loans
            best[lid] = raw
        elif _period_key(raw) > _period_key(best[lid]):
            best[lid] = raw
    tape = collapse_latest([normalize_row(r) for r in best.values()])
    write_loans_csv(out_csv, tape)
    return len(tape)
