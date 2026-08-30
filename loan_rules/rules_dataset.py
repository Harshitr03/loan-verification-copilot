from __future__ import annotations
from types import MappingProxyType
from loan_rules.base import Rule, Scope, bundle_from, violation_from
from loan_rules.registry import register


# --- selection helpers (respect an `avoid` set of row_uids) ----------------
def _eligible_indices(ds, avoid):
    avoid = avoid or set()
    idxs = [i for i, l in enumerate(ds.loans) if l["row_uid"] not in avoid]
    return idxs if len(idxs) >= 2 else list(range(len(ds.loans)))


def _pick_two(ds, rng, avoid):
    cands = _eligible_indices(ds, avoid)
    i, j = rng.choice(cands, size=2, replace=False)
    return int(i), int(j)


def _pick_one(ds, rng, avoid):
    return int(rng.choice(_eligible_indices(ds, avoid)))


# --- duplicate_loan_id -----------------------------------------------------
def _dupid_check(ds, ctx, params):
    out = []
    for loan in ds.loans:
        if ctx["loan_id_counts"][loan.get("loan_id")] > 1:
            out.append(violation_from(loan, "duplicate_loan_id", "loan_id",
                                      loan.get("loan_id"), "unique",
                                      "loan_id is duplicated", severity="high"))
    return out


def _dupid_corrupt(ds, rng, params, avoid=None):
    i, j = _pick_two(ds, rng, avoid)                          # both outside `avoid`
    victim, source = ds.loans[i], ds.loans[j]
    original = victim["loan_id"]
    victim["loan_id"] = source["loan_id"]                     # collide (loan_id mutated)
    dup = source["loan_id"]
    bundles = [
        bundle_from(victim, "duplicate_loan_id", "loan_id", dup, "unique",
                    "loan_id is duplicated", original=original),        # mutated member
        bundle_from(source, "duplicate_loan_id", "loan_id", dup, "unique",
                    "loan_id is duplicated", original=dup),             # unmutated partner
    ]
    return ds, bundles


register(Rule("duplicate_loan_id", Scope.DATASET, "high", MappingProxyType({}),
              "loan_id is duplicated", _dupid_check, _dupid_corrupt))


# --- duplicate_borrower_combo ----------------------------------------------
def _combo_key(l):
    return (l.get("borrower_id"), str(l.get("original_principal")), str(l.get("origination_date")))


def _combo_check(ds, ctx, params):
    out = []
    for loan in ds.loans:
        if loan.get("borrower_id") is None:      # null borrower can't form a "duplicate combo"
            continue
        if ctx["combo_counts"][_combo_key(loan)] > 1:
            out.append(violation_from(loan, "duplicate_borrower_combo", "borrower_id",
                                      loan.get("borrower_id"), "unique combo",
                                      "duplicate borrower+amount+origination combo"))
    return out


def _combo_corrupt(ds, rng, params, avoid=None):
    i, j = _pick_two(ds, rng, avoid)                          # both outside `avoid`
    victim, source = ds.loans[i], ds.loans[j]
    original = {k: victim[k] for k in ("borrower_id", "original_principal", "origination_date")}
    for k in ("borrower_id", "original_principal", "origination_date"):
        victim[k] = source[k]
    return ds, [
        bundle_from(victim, "duplicate_borrower_combo", "borrower_id", victim["borrower_id"],
                    "unique combo", "duplicate borrower combo", original=str(original)),
        bundle_from(source, "duplicate_borrower_combo", "borrower_id", source["borrower_id"],
                    "unique combo", "duplicate borrower combo", original=source["borrower_id"]),
    ]


register(Rule("duplicate_borrower_combo", Scope.DATASET, "medium", MappingProxyType({}),
              "duplicate borrower+amount+origination combo", _combo_check, _combo_corrupt))


# --- suspicious_borrower_repeat --------------------------------------------
def _repeat_check(ds, ctx, params):
    out = []
    for loan in ds.loans:
        if loan.get("borrower_id") is None:      # null borrower is "unknown", not "repeated"
            continue
        if ctx["borrower_counts"][loan.get("borrower_id")] > params["max_repeats"]:
            out.append(violation_from(loan, "suspicious_borrower_repeat", "borrower_id",
                                      loan.get("borrower_id"), f"<= {params['max_repeats']} loans",
                                      "borrower appears suspiciously often", severity="low"))
    return out


def _repeat_corrupt(ds, rng, params, avoid=None):   # appends fresh rows; `avoid` unused
    tag = int(rng.integers(1_000_000_000))
    bid = f"BRREP{tag:09d}"
    template = dict(ds.loans[int(rng.integers(len(ds.loans)))])   # realistic base fields
    bundles = []
    for k in range(params["max_repeats"] + 2):
        new = dict(template)
        new["row_uid"] = f"UREP{tag:09d}-{k}"
        new["loan_id"] = f"LNREP{tag:09d}-{k}"
        new["borrower_id"] = bid
        ds.loans.append(new)
        bundles.append(bundle_from(new, "suspicious_borrower_repeat", "borrower_id", bid,
                                   f"<= {params['max_repeats']}",
                                   "borrower appears suspiciously often", original=bid))
    return ds, bundles


register(Rule("suspicious_borrower_repeat", Scope.DATASET, "low",
              MappingProxyType({"max_repeats": 3}),
              "borrower appears suspiciously often", _repeat_check, _repeat_corrupt))


# --- cross-file rules ------------------------------------------------------
from decimal import Decimal


def _conflict_check(ds, ctx, params):
    out = []
    for loan in ds.loans:
        srv = ctx["servicer_by_loan"].get(loan.get("loan_id"))
        if not srv:
            continue
        for f in params["fields"]:
            if f in srv and str(srv[f]) != str(loan.get(f)):
                out.append(violation_from(loan, "source_conflict", f, loan.get(f),
                                          "match servicer_update",
                                          f"{f} conflicts with servicer_update",
                                          sibling=srv[f]))
                break
    return out


def _conflict_corrupt(ds, rng, params, avoid=None):
    loan = ds.loans[_pick_one(ds, rng, avoid)]                  # pick by index, outside `avoid`
    srv = next((s for s in ds.servicer_updates if s["loan_id"] == loan["loan_id"]), None)
    if srv is None:
        srv = {"loan_id": loan["loan_id"], "current_balance": loan["current_balance"],
               "interest_rate": loan["interest_rate"], "payment_status": loan["payment_status"]}
        ds.servicer_updates.append(srv)
    f = params["fields"][0]                                     # current_balance
    srv[f] = Decimal(str(loan[f])) + Decimal("77777.00")
    return ds, [bundle_from(loan, "source_conflict", f, loan.get(f), "match servicer_update",
                            f"{f} conflicts with servicer_update", sibling=srv[f],
                            original=loan.get(f))]


register(Rule("source_conflict", Scope.DATASET, "medium",
              MappingProxyType({"fields": ["current_balance", "interest_rate", "payment_status"]}),
              "value conflicts with servicer_update", _conflict_check, _conflict_corrupt))


def _doc_check(ds, ctx, params):
    return [violation_from(loan, "document_status_present", "document_status", None,
                           "present in manifest", "loan missing from document_manifest")
            for loan in ds.loans if loan.get("loan_id") not in ctx["manifest_ids"]]


def _doc_corrupt(ds, rng, params, avoid=None):
    loan = ds.loans[_pick_one(ds, rng, avoid)]                  # pick by index, outside `avoid`
    ds.manifest = [m for m in ds.manifest if m["loan_id"] != loan["loan_id"]]
    return ds, [bundle_from(loan, "document_status_present", "document_status", None,
                            "present in manifest", "loan missing from document_manifest",
                            original="COMPLETE")]


register(Rule("document_status_present", Scope.DATASET, "medium", MappingProxyType({}),
              "loan missing from document_manifest", _doc_check, _doc_corrupt))
