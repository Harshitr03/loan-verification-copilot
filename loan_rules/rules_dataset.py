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
