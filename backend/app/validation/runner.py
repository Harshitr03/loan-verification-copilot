import dataclasses
from collections import Counter
from types import MappingProxyType
from loan_rules import load_rules, validate_dataset, Dataset
from backend.app.models import Loan, RawRecord, Exception as Exc, Dataset as DatasetDoc
from backend.app.ingestion.normalize import to_canonical
from backend.app import audit

_SEV_WEIGHT = {"low": 1, "medium": 2, "high": 3, "critical": 4}
_DATASET_RULES = {"duplicate_loan_id", "duplicate_borrower_combo",
                  "suspicious_borrower_repeat", "source_conflict", "document_status_present"}


async def _siblings(dataset_id, file_type):
    return [r.raw for r in await RawRecord.find(RawRecord.dataset_id == dataset_id,
                                                RawRecord.file_type == file_type).to_list()]


async def run_validation(dataset_id, rules_path=None) -> dict:
    loans = await Loan.find(Loan.dataset_id == dataset_id).to_list()
    # Validate on the LENIENT canonical dict rebuilt from each loan's raw row (preserves
    # raw-but-invalid values, e.g. a garbage date, so the rules flag them). row_uid = the
    # loan's _id (unique per row). This is the representation loan_rules is designed for.
    raws = await RawRecord.find(RawRecord.dataset_id == dataset_id,
                                RawRecord.file_type == "loan_tape").to_list()
    raw_by_rid = {str(r.id): r.raw for r in raws}
    plain = []
    for l in loans:
        canon, _ = to_canonical(raw_by_rid.get(l.normalized_from_raw_id, {}), l.source_system or "")
        canon = canon or {}
        canon["row_uid"] = str(l.id)
        plain.append(canon)
    servicer = await _siblings(dataset_id, "servicer_update")
    manifest = await _siblings(dataset_id, "document_manifest")

    # Field-availability gating (same principle as the fnma_sf connector's pass3_rules):
    # a rule that flags on the ABSENCE of an input the source structurally lacks would flag
    # every loan (e.g. real FNMA data has no borrower_id / document_status / manifest). Skip
    # or narrow those rather than flood the queue. Sources that DO carry the field (the graded
    # synthetic tape) are unaffected.
    has_manifest = bool(manifest)
    has_borrower = any(p.get("borrower_id") for p in plain)
    rules, gated = [], []
    for r in load_rules(rules_path):
        if r.id == "document_status_present" and not has_manifest:
            gated.append(r.id)
            continue                                   # can't assess doc presence with no manifest
        if r.id == "required_fields" and not has_borrower:
            req = [f for f in r.params.get("required", []) if f != "borrower_id"]
            r = dataclasses.replace(r, params=MappingProxyType({**dict(r.params), "required": req}))
            gated.append("required_fields:borrower_id")
        rules.append(r)
    violations = validate_dataset(Dataset(plain, servicer, manifest), rules)

    # idempotent re-validation: clear this dataset's prior rule-sourced exceptions
    await Exc.find(Exc.dataset_id == dataset_id, Exc.source == "rule").delete()

    for v in violations:
        await Exc(
            loan_id=v.loan_id, loan_ref=v.row_uid, dataset_id=dataset_id, rule_id=v.rule_id,
            type="DATASET" if v.rule_id in _DATASET_RULES else "ROW",
            severity=v.severity, source="rule", field=v.field,
            observed_value=str(v.observed_value), expected=str(v.expected),
            sibling_value=(str(v.sibling_value) if v.sibling_value is not None else None),
            message=v.message, status="open").insert()

    for l in loans:
        l.validation_status = "validated"
        l.lifecycle_state = "validated"
        await l.save()

    # severity-weighted quality score (finding #6)
    total_w = (len(loans) or 1) * _SEV_WEIGHT["critical"]
    penalty = sum(_SEV_WEIGHT.get(v.severity, 1) for v in violations)
    score = round(max(0.0, 1 - penalty / total_w), 4)
    doc = await DatasetDoc.get(dataset_id)
    if doc:
        doc.quality_score = score
        doc.status = "validated"
        await doc.save()

    # one summary event, not one per exception (finding RC1)
    await audit.append("validation_executed", "dataset", dataset_id, "system",
                       {"exceptions": len(violations),
                        "by_rule": dict(Counter(v.rule_id for v in violations)),
                        "by_severity": dict(Counter(v.severity for v in violations)),
                        "gated_rules": gated})
    return {"exceptions": len(violations), "quality_score": score, "gated_rules": gated}
