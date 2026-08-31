# P2 — Ingestion + Validation Wiring (Modules A + B) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire Module A (upload → raw_records → normalize → loans + failed rows + lineage + summary) and Module B (run the **existing** 15 `loan_rules` over a dataset → `exceptions`) to the P1 backend, proving correctness end-to-end against the generator's ground-truth oracle.

**Architecture:** `backend/app/ingestion` parses uploads with pandas (every row preserved to `raw_records`), normalizes to the canonical schema, and persists `loans` with lineage. `backend/app/validation/runner.py` builds a `loan_rules.Dataset` from a dataset's loans and runs `load_rules(...)` — the engine is imported, never reimplemented. Every graded event appends to the P1 audit chain.

**Tech Stack:** pandas, `loan_rules` (`load_rules`, `validate_dataset`, `Dataset`), `data._serialize.CANONICAL_COLUMNS`, FastAPI upload (`UploadFile`), P1 models/audit.

**Spec:** parent §4 (canonical schema), §6 (Module A), §7 (Module B), §11. Depends on **P1 green**. Roadmap P2.

## Global Constraints

- **Reuse the engine:** validation calls `loan_rules.load_rules(path)` + `validate_dataset(Dataset(...), rules)`. No rule logic here. The exception record's `{rule_id, field, observed_value, expected, sibling_value?, message}` is the loan_rules `Violation` shape verbatim (spec §5).
- **Three-file ingestion (spec §6, finding RC2):** a dataset is a **`loan_tape` (required) + `servicer_update` (optional) + `document_manifest` (optional)** bundle uploaded together. Sibling rows are stored in `raw_records` tagged `file_type`; the runner reconstructs `Dataset(loans, servicer_updates, manifest)` so **all 15 rule types fire** (incl. `source_conflict`, `document_status_present`) and Module D's "compare" op has real conflicts. The oracle test then holds with **zero carve-outs**.
- **Surrogate key crosses into the backend (finding RC3):** validation keys off each loan's Mongo `_id` as `row_uid` (genuinely unique per row) — **never `loan_id`** (which `duplicate_loan_id` deliberately collides). The `Exception` stores both `loan_id` (business key, for display/grouping) and `loan_ref = str(loan.id)` (the exact row).
- **Lineage is mandatory:** every `Loan` carries `dataset_id` + `normalized_from_raw_id`; every raw row is stored before normalization.
- **Failed rows never crash import:** a row that cannot be normalized becomes a failure record with a reason; import continues.
- **Graded path is `loan_tape`:** P2 handles the `loan_tape` profile end-to-end. Panel (`sf_performance_panel`) ingestion is P9 (Phase 2) — out of scope here.
- **Bulk-validation audit (finding RC1 decision):** validation appends **one** `validation_executed` summary event carrying the rule/severity breakdown — **not** one event per exception (per-exception detail lives in the queryable `exceptions` collection; reviewer *actions* are per-event in P3).
- **Serialization for API:** Decimals/dates serialize via the same rules as `data._serialize.format_value` where values cross the API boundary (reuse it).
- All new endpoints require the `data_operator` role except reads (spec §3).

---

## File Structure

```
backend/app/
  ingestion/
    __init__.py
    parse.py          # read_upload(bytes, filename) -> list[dict] (pandas, raw rows)
    normalize.py      # to_canonical(raw, source_system) -> (canon|None, reason|None)
    service.py        # ingest_dataset(...) orchestration (raw_records + loans + lineage + summary)
  validation/
    __init__.py
    runner.py         # run_validation(dataset_id) -> summary; writes exceptions
  api/
    datasets.py       # POST /datasets, POST /datasets/:id/validate, GET /datasets/:id
backend/tests/
  test_parse.py  test_normalize_backend.py  test_ingest_service.py
  test_validation_runner.py  test_datasets_api.py
```

---

### Task 1: `parse.read_upload` — pandas raw parse

**Files:** Create `backend/app/ingestion/__init__.py`, `backend/app/ingestion/parse.py`; Test `backend/tests/test_parse.py`.

**Interfaces:** Produces `read_upload(content: bytes, filename: str) -> list[dict]` — pandas `read_csv` (dtype=str, keep_default_na=False) → list of raw row dicts preserving original column names; `row_number` is the 1-based source index (added by the caller).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_parse.py
from backend.app.ingestion.parse import read_upload


def test_read_upload_preserves_columns_and_values():
    csv = b"loan_id,current_balance\nLN1,100.00\nLN2,\n"
    rows = read_upload(csv, "loan_tape.csv")
    assert rows == [{"loan_id": "LN1", "current_balance": "100.00"},
                    {"loan_id": "LN2", "current_balance": ""}]     # blanks kept, not NaN
```

- [ ] **Step 2: Run to verify fail.**

- [ ] **Step 3: Implement**

```python
# backend/app/ingestion/parse.py
import io
import pandas as pd


def read_upload(content: bytes, filename: str) -> list[dict]:
    df = pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False)
    return df.to_dict(orient="records")
```

- [ ] **Step 4: Run to verify pass.** - [ ] **Step 5: Commit** `feat(ingestion): pandas raw upload parser`.

---

### Task 2: `normalize.to_canonical` — raw → canonical (spec §4)

**Files:** Create `backend/app/ingestion/normalize.py`; Test `backend/tests/test_normalize_backend.py`.

**Interfaces:** Produces `to_canonical(raw: dict, source_system: str) -> tuple[dict|None, str|None]` — returns `(canonical_loan_dict, None)` on success or `(None, reason)` on failure. Handles: date parsing (multiple formats → `date`), currency strings → `Decimal`, enum canonicalization (`FXD`/`Fixed`→`FIXED`, etc.), state-name → 2-letter, whitespace/case cleanup. Requires `loan_id`; missing/unparusable required fields → failure reason.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_normalize_backend.py
from datetime import date
from decimal import Decimal
from backend.app.ingestion.normalize import to_canonical


def test_normalizes_messy_row():
    raw = {"loan_id": " LN1 ", "borrower_id": "BR1", "loan_type": "Fixed",
           "origination_date": "01/15/2020", "original_principal": "$250,000.00",
           "borrower_state": "California", "interest_rate": "5.25%", "payment_status": "current"}
    canon, reason = to_canonical(raw, "ORIG_SYS")
    assert reason is None
    assert canon["loan_id"] == "LN1" and canon["loan_type"] == "FIXED"
    assert canon["origination_date"] == date(2020, 1, 15)
    assert canon["original_principal"] == Decimal("250000.00")
    assert canon["borrower_state"] == "CA" and canon["interest_rate"] == Decimal("5.25")
    assert canon["payment_status"] == "CURRENT" and canon["source_system"] == "ORIG_SYS"


def test_already_canonical_generated_tape_row_is_near_identity():
    raw = {"loan_id": "LN00001", "loan_type": "FIXED", "origination_date": "2020-01-15",
           "original_principal": "250000.00", "borrower_state": "CA", "interest_rate": "5.25",
           "payment_status": "CURRENT", "current_balance": "200000.00", "days_past_due": "0"}
    canon, reason = to_canonical(raw, "ORIG_SYS")
    assert reason is None and canon["current_balance"] == Decimal("200000.00")


def test_missing_loan_id_is_a_failure():
    canon, reason = to_canonical({"loan_id": "", "original_principal": "100"}, "S")
    assert canon is None and "loan_id" in reason
```

- [ ] **Step 2: Run to verify fail.**

- [ ] **Step 3: Implement** — `normalize.py` with helpers: `_clean(s)` (strip), `_money(s)` (strip `$ , %` → `Decimal`, `InvalidOperation`→raise), `_date(s)` (try ISO, `%m/%d/%Y`, `%d-%m-%Y`), `_enum` maps (`LOAN_TYPE={"FXD":"FIXED","FIXED":"FIXED","FIXED RATE":"FIXED","ARM":"ARM",...}`, `PURPOSE`, `STATUS`), `STATE_NAMES` (full-name→code, plus pass-through valid 2-letter). `to_canonical` builds the 21 canonical keys, catches per-field parse errors into `reason`, requires `loan_id` non-empty. Return `(dict, None)` or `(None, reason)`.

```python
# core skeleton (fill enum maps from spec §4)
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

def _money(s):
    s = s.strip().replace("$", "").replace(",", "").replace("%", "")
    return Decimal(s) if s else None

_DATE_FMTS = ("%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d")
def _date(s):
    s = s.strip()
    if not s:
        return None
    for f in _DATE_FMTS:
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            continue
    raise ValueError(f"unparseable date {s!r}")

LOAN_TYPE = {"FIXED": "FIXED", "FXD": "FIXED", "FIXED RATE": "FIXED", "ARM": "ARM",
             "ADJUSTABLE": "ARM"}
def _enum(val, table):
    return table.get(val.strip().upper()) if val and val.strip() else None

def to_canonical(raw, source_system):
    try:
        lid = raw.get("loan_id", "").strip()
        if not lid:
            return None, "missing loan_id"
        canon = {
            "loan_id": lid,
            "borrower_id": raw.get("borrower_id", "").strip() or None,
            "loan_type": _enum(raw.get("loan_type", ""), LOAN_TYPE),
            "origination_date": _date(raw.get("origination_date", "")),
            "maturity_date": _date(raw.get("maturity_date", "")),
            "original_principal": _money(raw.get("original_principal", "")),
            "current_balance": _money(raw.get("current_balance", "")),
            "interest_rate": _money(raw.get("interest_rate", "")),
            "term_months": int(raw["term_months"]) if raw.get("term_months", "").strip() else None,
            "borrower_state": _state(raw.get("borrower_state", "")),
            "loan_purpose": _enum(raw.get("loan_purpose", ""), PURPOSE),
            "credit_grade": raw.get("credit_grade", "").strip() or None,
            "employment_length": raw.get("employment_length", "").strip() or None,
            "income_band": raw.get("income_band", "").strip() or None,
            "payment_status": _enum(raw.get("payment_status", ""), STATUS),
            "days_past_due": int(raw["days_past_due"]) if raw.get("days_past_due", "").strip() else None,
            "servicer_name": raw.get("servicer_name", "").strip() or None,
            "last_payment_date": _date(raw.get("last_payment_date", "")),
            "last_updated_at": _date(raw.get("last_updated_at", "")),
            "document_status": raw.get("document_status", "").strip() or None,
            "source_system": source_system,
        }
        return canon, None
    except (ValueError, InvalidOperation) as e:
        return None, str(e)
```

Define `PURPOSE`, `STATUS`, `_state`/`STATE_NAMES` (full names → codes; valid 2-letter pass-through) per spec §4.

- [ ] **Step 4: Run to verify pass.** - [ ] **Step 5: Commit** `feat(ingestion): canonical normalization with lineage-safe failures`.

---

### Task 3: `ingest_dataset` service — raw + loans + summary

**Files:** Create `backend/app/ingestion/service.py`; Test `backend/tests/test_ingest_service.py`.

**Interfaces:** Produces `async ingest_dataset(loan_tape: tuple[str,bytes], source_system, uploaded_by, servicer_update: tuple[str,bytes]|None = None, document_manifest: tuple[str,bytes]|None = None) -> Dataset` — creates `Dataset` (status `imported`), stores every `loan_tape` row (`RawRecord`, `file_type="loan_tape"`), normalizes each → `Loan`s (lifecycle `imported`, `normalized_from_raw_id`); stores sibling rows as `RawRecord`s tagged `file_type="servicer_update"`/`"document_manifest"` (no normalization — they feed the rule context as-is); records `failures: list[{row_number, reason}]` (add to `Dataset` model), sets `row_count/imported_count/failed_count`; appends **one** audit `file_uploaded` summary event (counts + which sibling files present) — not per-record (RC1 principle).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_ingest_service.py
import pytest
from backend.app.ingestion.service import ingest_dataset
from backend.app.models import Loan, RawRecord, AuditEntry


@pytest.mark.asyncio
async def test_ingest_stores_raw_loans_counts_and_siblings(db):
    tape = b"loan_id,original_principal,origination_date\nLN1,100.00,2020-01-15\n,50,2020-01-15\n"
    srv = b"loan_id,current_balance\nLN1,90.00\n"
    man = b"loan_id,document_status\nLN1,COMPLETE\n"
    ds = await ingest_dataset(("tape.csv", tape), "ORIG_SYS", "op",
                              servicer_update=("srv.csv", srv), document_manifest=("man.csv", man))
    assert ds.row_count == 2 and ds.imported_count == 1 and ds.failed_count == 1
    loans = await Loan.find(Loan.dataset_id == str(ds.id)).to_list()
    assert len(loans) == 1 and loans[0].loan_id == "LN1" and loans[0].normalized_from_raw_id
    assert await RawRecord.find(RawRecord.dataset_id == str(ds.id),
                                RawRecord.file_type == "servicer_update").count() == 1
    assert ds.failures[0]["reason"]      # the empty-loan_id row
    # one summary event, not per-record:
    assert await AuditEntry.find(AuditEntry.event_type == "file_uploaded").count() == 1
```

- [ ] **Step 2: Run to verify fail.**

- [ ] **Step 3: Implement** `service.py` — parse (Task 1) + normalize (Task 2) the tape; store sibling rows raw with `file_type`; thread `raw._id` into `Loan.normalized_from_raw_id`; compute counts; append one summary `file_uploaded`. Add `failures: list[dict] = []` and `file_type` (on `RawRecord`) to the models.

- [ ] **Step 4: Run to verify pass.** - [ ] **Step 5: Commit** `feat(ingestion): dataset ingest service with lineage + failed-row summary`.

---

### Task 4: `POST /datasets` + `GET /datasets/:id` (Module A endpoints)

**Files:** Create `backend/app/api/datasets.py`; mount in `main`; Test `backend/tests/test_datasets_api.py`.

**Interfaces:** Produces `POST /datasets` (multipart: `loan_tape` file [required], `servicer_update` file [optional], `document_manifest` file [optional], `source_system` form field; role `data_operator`) → `{dataset_id, row_count, imported_count, failed_count}`; `GET /datasets` → import-history list (`{items}` newest-first; **owned here**, finding 4b) for the operator; `GET /datasets/:id` → summary incl. `failures` + `quality_score` (once validated).

- [ ] **Step 1: Write the failing test** — operator uploads the 3 files via `client` + operator token, asserts 200 + counts; `GET /datasets` lists it; a `data_consumer` token on `POST /datasets` gets 403.

- [ ] **Step 2: Run fail.** - [ ] **Step 3: Implement** router: three `UploadFile | None` params + `source_system: str = Form(...)`, `require_role("data_operator")`, reading each file's bytes and calling `ingest_dataset`. Add `GET /datasets` (list) + `GET /datasets/:id`. - [ ] **Step 4: Run pass.** - [ ] **Step 5: Commit** `feat(api): 3-file dataset upload + import-history + summary endpoints`.

Uses P1's `auth_headers(role)`/`operator_headers`/`consumer_headers` conftest fixtures.

---

### Task 5: Validation runner — run the 15 rules → exceptions

**Files:** Create `backend/app/validation/__init__.py`, `backend/app/validation/runner.py`; Test `backend/tests/test_validation_runner.py`.

**Interfaces:** Produces `async run_validation(dataset_id, rules_path=None) -> dict` — builds `loan_rules.Dataset(loans, servicer_updates, manifest)` where `loans` are the dataset's `Loan`s (each with **`row_uid = str(loan.id)`** and a back-map to its `_id`), and `servicer_updates`/`manifest` are reconstructed from the dataset's sibling `raw_records` (finding RC2). Runs `validate_dataset(ds, load_rules(rules_path))`, writes an `Exception` per `Violation` (`severity` from the rule, `source="rule"`, `type=rule.scope.name`, **`loan_ref` = the loan `_id` resolved from `v.row_uid`**), sets each loan's `validation_status="validated"`, sets `dataset.quality_score` (**severity-weighted**, finding #6), appends **one** `validation_executed` summary event with the rule/severity breakdown (finding RC1). Returns `{exceptions, quality_score}`.

- [ ] **Step 1: Write the failing test (the oracle test — now carve-out-free)**

```python
# backend/tests/test_validation_runner.py
import csv, pytest
from data.generate import generate
from backend.app.ingestion.service import ingest_dataset
from backend.app.validation.runner import run_validation
from backend.app.models import Exception as Exc, AuditEntry


@pytest.mark.asyncio
async def test_runner_reproduces_full_ground_truth_superset(tmp_path, db):
    generate(str(tmp_path), rows=400, seed=7)     # writes tape + servicer_update + manifest + rules + ground truth
    read = lambda n: (n, (tmp_path / n).read_bytes())
    ds = await ingest_dataset(read("loan_tape.csv"), "ORIG_SYS", "op",
                              servicer_update=read("servicer_update.csv"),
                              document_manifest=read("document_manifest.csv"))
    await run_validation(str(ds.id), rules_path=str(tmp_path / "validation_rules.json"))
    found = {(e.loan_id, e.rule_id) async for e in Exc.find(Exc.dataset_id == str(ds.id))}
    gt = set()
    with open(tmp_path / "ground_truth_exceptions.csv") as f:
        for r in csv.DictReader(f):
            gt.add((r["loan_id"], r["rule_id"]))
    # NO carve-outs: 3-file ingestion + row_uid=_id means all 15 rule types (incl.
    # source_conflict, document_status_present, duplicate_loan_id) are detectable.
    assert gt <= found, f"missed: {gt - found}"
    # one summary validation event, not one per exception:
    assert await AuditEntry.find(AuditEntry.event_type == "validation_executed").count() == 1
    assert await AuditEntry.find(AuditEntry.event_type == "exception_created").count() == 0
```

- [ ] **Step 2: Run to verify fail.**

- [ ] **Step 3: Implement** `runner.py`:

```python
from collections import Counter
from loan_rules import load_rules, validate_dataset, Dataset
from backend.app.models import Loan, RawRecord, Exception as Exc, Dataset as DatasetDoc
from backend.app import audit

_SEV_WEIGHT = {"low": 1, "medium": 2, "high": 3, "critical": 4}

async def _siblings(dataset_id, file_type):
    return [r.raw for r in await RawRecord.find(RawRecord.dataset_id == dataset_id,
                                                RawRecord.file_type == file_type).to_list()]

async def run_validation(dataset_id, rules_path=None):
    loans = await Loan.find(Loan.dataset_id == dataset_id).to_list()
    by_uid = {str(l.id): l for l in loans}
    plain = [{**l.model_dump(), "row_uid": str(l.id)} for l in loans]   # _id is the surrogate key
    servicer = await _siblings(dataset_id, "servicer_update")
    manifest = await _siblings(dataset_id, "document_manifest")
    rules = load_rules(rules_path)
    violations = validate_dataset(Dataset(plain, servicer, manifest), rules)
    sev_by_id = {r.id: r.severity for r in rules}
    for v in violations:
        loan = by_uid.get(v.row_uid)
        await Exc(loan_id=v.loan_id, loan_ref=v.row_uid, dataset_id=dataset_id, rule_id=v.rule_id,
                  type="DATASET" if v.rule_id in {"duplicate_loan_id","duplicate_borrower_combo",
                       "suspicious_borrower_repeat","source_conflict","document_status_present"} else "ROW",
                  severity=v.severity, source="rule", field=v.field,
                  observed_value=str(v.observed_value), expected=str(v.expected),
                  sibling_value=(str(v.sibling_value) if v.sibling_value is not None else None),
                  message=v.message, status="open").insert()
    for l in loans:
        l.validation_status = "validated"; l.lifecycle_state = "validated"; await l.save()
    # severity-weighted quality score (finding #6)
    total_w = (len(loans) or 1) * _SEV_WEIGHT["critical"]
    penalty = sum(_SEV_WEIGHT.get(v.severity, 1) for v in violations)
    score = round(max(0.0, 1 - penalty / total_w), 4)
    doc = await DatasetDoc.get(dataset_id)
    if doc:
        doc.quality_score = score; await doc.save()
    breakdown = dict(Counter(v.rule_id for v in violations))
    await audit.append("validation_executed", "dataset", dataset_id, "system",
                       {"exceptions": len(violations), "by_rule": breakdown,
                        "by_severity": dict(Counter(v.severity for v in violations))})
    return {"exceptions": len(violations), "quality_score": score}
```

Note: `model_dump()` yields Decimals/dates as Python types so the rules' `isinstance(v, Decimal)` / `date` checks hold. Sibling `raw` dicts are the CSV rows as strings — `source_conflict` compares `str(srv[f]) != str(loan[f])`, which matches the generator's string-serialized servicer values, and `document_status_present` keys on `loan_id ∈ {m["loan_id"]}`. Add `loan_ref: Optional[str]` to the `Exception` model.

- [ ] **Step 4: Run to verify pass.** - [ ] **Step 5: Commit** `feat(validation): 3-file runner, _id surrogate key, summary audit, weighted score`.

---

### Task 6: `POST /datasets/:id/validate`

**Files:** Modify `backend/app/api/datasets.py`; Test extends `test_datasets_api.py`.

**Interfaces:** `POST /datasets/:id/validate` (role `data_operator`) → `{exceptions, quality_score}` by calling `run_validation`. Uses the dataset's own uploaded `validation_rules.json` if present else defaults.

- [ ] Standard TDD: operator uploads tape, validates, gets exception count > 0 and a quality_score in (0,1]; consumer 403.
- [ ] Commit `feat(api): dataset validate endpoint`.

---

## Self-Review

**1. Spec coverage:** §6 three-file upload/raw/normalize/failed-rows/summary/lineage → T1–T4; §6.1 `loan_tape` profile → whole plan (panel deferred to P9); §7 the 15 rules data-driven with severity + severity-weighted score → T5; §11 `POST /datasets`, `GET /datasets`, `POST /datasets/:id/validate` → T4,T6. §4 canonical schema → T2.

**Review fixes folded in:** RC2 (3-file ingestion → all 15 rules, zero carve-outs) → constraints + T3,T4,T5; RC3 (`row_uid = _id`, `Exception.loan_ref`) → T5; RC1 (one `validation_executed` summary event, no per-exception audit) → T5; #6 (severity-weighted `quality_score`) → T5; 4b (`GET /datasets` owned here) → T4.

**2. Placeholder scan:** enum maps (`PURPOSE`/`STATUS`/`STATE_NAMES`) named with §4 construction rules; `_state` specified; runner + siblings + score are complete code. No TODO.

**3. Type/name consistency:** `ingest_dataset` (T3, now 3-file) consumed by T4; `run_validation` (T5) consumed by T6; imports `loan_rules.load_rules/validate_dataset/Dataset` + P1 `audit.append`/models as defined; `Exception.loan_ref` added (P1 model note). `RawRecord.file_type` added (T3).

## Notes for the executor
- **Surrogate key:** `row_uid = str(loan.id)` (unique per row) — never `loan_id`. This is what lets `duplicate_loan_id` work and removes every oracle carve-out; do not revert it to `loan_id`.
- **Siblings feed the context as raw strings:** the generator serializes servicer/manifest values as strings, and `source_conflict`/`document_status_present` compare/lookup by string — so no sibling normalization is needed. If a future non-generator source needs typed siblings, normalize then.
- **Model additions this plan requires (in P1 models):** `Dataset.failures: list[dict]`, `RawRecord.file_type: str`, `Exception.loan_ref: Optional[str]` — add them to the P1 model definitions when executing P1, or as a small model migration at the start of P2.
- Import-purity: the backend imports `loan_rules`/`data`; the reverse must never happen (loan_rules stays app-free).
