# FNMA SF Connector + Grain-Aware Validation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingest the real FNMA Single-Family Loan Performance file (loan-month panel), validate it grain-appropriately (Pass 1), collapse it to a loan tape (Pass 2), and feed that into the **unchanged** 15 loan-grain rules (Pass 3) — as an optional stretch source that never touches the graded synthetic path.

**Architecture:** A standalone, import-pure `fnma_sf` package: `layout` (verified glossary positions) → `parse` (headerless pipe, leading-pipe indexing) → `normalize` (map + derive canonical fields, null-safe) → `panel` (Pass 1: structural checks + the row-local rule subset) → `collapse` (Pass 2: latest month per loan) → `pipeline` (Pass 3: run the 15 loan-grain rules on the collapsed tape) + a streaming demo-slice builder. It reuses `loan_rules` (`Rule.profiles`, `validate_dataset`, `Dataset`) and `data._serialize` (`CANONICAL_COLUMNS`, `write_loans_csv`); it never modifies them.

**Tech Stack:** Python 3.12, stdlib only for parsing (`csv` not used — the file is `|`-delimited and headerless), `loan_rules` + `data` packages from the generator build, pytest.

**Spec:** `docs/specs/2026-08-27-loan-verification-copilot-design.md` §6.1–6.3, §7 (profiles), §12.2, §17.

## Global Constraints

- **DEPENDS ON the generator plan (`docs/plans/2026-08-29-data-generator.md`) being executed first.** This plan imports, from that build: `loan_rules` (`Rule`, `Scope`, `Dataset`, `load_rules`, `validate_dataset`, `violation_from`, and `Rule.profiles`) and `data._serialize` (`CANONICAL_COLUMNS`, `write_loans_csv`). Do not start before `pytest -q` is green on that plan.
- **`fnma_sf` is a standalone top-level package**, editable-installed via the existing root `pyproject.toml` (add `"fnma_sf"` to `[tool.setuptools] packages`). Import-pure: no Mongo/FastAPI. `backend/app/ingestion/` will later be a thin adapter that calls it (out of scope here).
- **Leading-pipe indexing (load-bearing):** the file has a leading `|`, so after `line.split('|')`, glossary field *N* is at `parts[N-1]` (`parts[0]` is the empty Reference Pool ID). All field access goes through one helper that encodes this; a test pins it against the real sample.
- **Profiles / field availability:** the panel pass (Pass 1) runs **only** rules whose `profiles` include `"sf_performance_panel"` (the 8 row-local rules, all `ROW`-scope). Pass 3 runs the loan-grain rules **unchanged** on the collapsed tape, but skips the 2 (`required_fields`, `document_status_present`) whose inputs this source structurally lacks and which flag on absence — 13 of 15 (see `pass3_rules`, Task 6). The rules' code is never modified; the graded synthetic path still runs all 15.
- **Real data has NO ground truth.** There is no oracle/superset test here. Tests assert **mapping and structural correctness** against the committed 8-loan sample and hand-built fixtures — never exception ground truth. Findings on real data are reviewer-gated; the synthetic package remains the graded oracle.
- **Canonical values are typed** (money `Decimal`, dates `datetime.date`, ints `int`) so the reused `loan_rules` checks operate correctly. MMYYYY dates are month-precision → `day=1`; empty → `None`.
- **`source_system = "FNMA_SF_LPD"`**, dataset `profile = "sf_performance_panel"`. `borrower_id`, `income_band`, `document_status` have no source → `None`, surfaced as **partial-import** fields (must not crash normalization).
- **Raw FNMA files are git-ignored** (already done). Only a small **collapsed** fixture derived from `sf-loan-performance-data-sample.csv` is committed. The 8-loan raw sample stays tracked for tests.

---

## File Structure

```
fnma_sf/
  __init__.py                # exports parse_line, normalize_row, validate_panel,
                             #   collapse_latest, ingest_panel, build_demo_tape
  layout.py                  # glossary field positions (verified) + field access helper
  parse.py                   # headerless pipe parser (leading-pipe indexing)
  normalize.py               # map + derive canonical panel dict; null-safe; row_uid
  panel.py                   # Pass 1: structural checks + row-local rule subset runner
  collapse.py                # Pass 2: latest-month-per-loan collapse
  pipeline.py                # Pass 3 orchestration + streaming demo-slice builder
tests/fnma_sf/
  test_parse.py              # leading-pipe indexing against the real sample
  test_normalize.py          # derivations (dates, credit bands, status, dpd, purpose, nulls)
  test_panel.py              # structural checks + row-local subset (identity rules excluded)
  test_collapse.py           # latest-month selection
  test_pipeline.py           # end-to-end on sample; Pass 3 runs 15 rules
  fixtures/
    collapsed_sample.csv     # committed 8-loan collapsed tape (built once from sample)
Makefile                     # add `fnma-demo` target
```

---

### Task 1: `fnma_sf` package + `layout.py` + `parse.py` (leading-pipe indexing)

**Files:**
- Create: `fnma_sf/__init__.py`, `fnma_sf/layout.py`, `fnma_sf/parse.py`
- Modify: `pyproject.toml` (add `fnma_sf` to packages)
- Test: `tests/fnma_sf/test_parse.py`

**Interfaces:**
- Produces: `POSITIONS: dict[str, int]` (canonical source name → glossary position); `field(parts, pos) -> str` (returns `parts[pos-1]`, `""` if out of range); `parse_line(line: str) -> dict` (raw string values keyed by canonical source name); `iter_rows(path) -> Iterator[dict]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/fnma_sf/test_parse.py
from fnma_sf.parse import parse_line, iter_rows

SAMPLE = "sf-loan-performance-data-sample.csv"


def test_leading_pipe_indexing_on_real_first_row():
    with open(SAMPLE) as f:
        rec = parse_line(next(f))
    # These exact values come from the real sample's first line; a naive parts[N]
    # (ignoring the leading pipe) would shift every field and fail here.
    assert rec["loan_id"] == "100023020488"
    assert rec["reporting_period"] == "082009"
    assert rec["interest_rate"] == "5.375"
    assert rec["original_principal"] == "55000.00"
    assert rec["term_months"] == "240"
    assert rec["origination_date"] == "082009"
    assert rec["maturity_date"] == "092029"
    assert rec["borrower_state"] == "OH"
    assert rec["loan_purpose"] == "C"
    assert rec["credit_score"] == "714"


def test_iter_rows_reads_all_panel_rows():
    # Robust to a missing final newline: compare against non-blank physical lines.
    with open(SAMPLE) as f:
        expected = sum(1 for line in f if line.strip())
    assert sum(1 for _ in iter_rows(SAMPLE)) == expected == 757
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/fnma_sf/test_parse.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fnma_sf'`

- [ ] **Step 3: Write minimal implementation**

```python
# fnma_sf/layout.py
# Glossary positions verified against crt-file-layout-and-glossary.xlsx (Combined Glossary).
# The file has a LEADING PIPE, so glossary field N lives at parts[N-1].
POSITIONS = {
    "loan_id": 2, "reporting_period": 3, "servicer_name": 6, "interest_rate": 9,
    "original_principal": 10, "current_balance": 12, "term_months": 13,
    "origination_date": 14, "maturity_date": 19, "borrower_state": 31,
    "loan_purpose": 27, "credit_score": 24, "zero_balance_code": 44,
    "delinquency": 40, "last_paid": 51, "amortization_type": 35,
}


def field(parts, pos):
    i = pos - 1                      # leading-pipe: glossary field N -> parts[N-1]
    return parts[i] if 0 <= i < len(parts) else ""
```

```python
# fnma_sf/parse.py
from __future__ import annotations
from fnma_sf.layout import POSITIONS, field


def parse_line(line: str) -> dict:
    parts = line.rstrip("\n").split("|")          # parts[0] == "" (leading pipe)
    return {name: field(parts, pos) for name, pos in POSITIONS.items()}


def iter_rows(path):
    with open(path) as f:
        for line in f:
            if line.strip():
                yield parse_line(line)
```

```python
# fnma_sf/__init__.py
from fnma_sf.parse import parse_line, iter_rows
__all__ = ["parse_line", "iter_rows"]
```

Add `"fnma_sf"` to `[tool.setuptools] packages` in `pyproject.toml` (now `["loan_rules", "fnma_sf"]`), then `pip install -e ".[dev]"`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pip install -e ".[dev]" && pytest tests/fnma_sf/test_parse.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml fnma_sf/ tests/fnma_sf/test_parse.py
git commit -m "feat(fnma_sf): headerless pipe parser with verified leading-pipe indexing"
```

---

### Task 2: `normalize.py` — map + derive canonical panel fields (null-safe)

**Files:**
- Create: `fnma_sf/normalize.py`
- Modify: `fnma_sf/__init__.py`
- Test: `tests/fnma_sf/test_normalize.py`

**Interfaces:**
- Consumes: `parse_line` (Task 1).
- Produces: pure derivations `mmyyyy(s) -> date|None`, `to_decimal(s) -> Decimal|None`, `credit_grade(fico) -> str|None` (A≥740, B≥680, C≥620, else D), `payment_status(zero_bal, delinq) -> str|None`, `days_past_due(delinq) -> int|None`, `loan_purpose(code) -> str|None` (P→PURCHASE, C→CASHOUT, R/U→REFI); `normalize_row(raw: dict) -> dict` producing a canonical **panel** loan dict with `row_uid=f"{loan_id}|{reporting_period}"`, `profile="sf_performance_panel"`, `source_system="FNMA_SF_LPD"`, and `_partial: list[str]` naming null-because-no-source fields; `is_failed(canon) -> bool` (missing `loan_id` or unparseable `reporting_period`/`origination_date`).

- [ ] **Step 1: Write the failing test**

```python
# tests/fnma_sf/test_normalize.py
from datetime import date
from decimal import Decimal
from fnma_sf.parse import parse_line
from fnma_sf.normalize import (mmyyyy, credit_grade, payment_status, days_past_due,
                               loan_purpose, loan_type, normalize_row, is_failed)


def test_mmyyyy_month_precision():
    assert mmyyyy("082009") == date(2009, 8, 1)
    assert mmyyyy("") is None and mmyyyy("13/40") is None


def test_credit_grade_bands():
    assert (credit_grade("740"), credit_grade("714"), credit_grade("650"),
            credit_grade("600"), credit_grade("")) == ("A", "B", "C", "D", None)


def test_payment_status_and_dpd():
    assert payment_status("01", "00") == "CLOSED"        # zero-bal present -> closed
    assert payment_status("", "00") == "CURRENT"
    assert payment_status("", "03") == "DELINQUENT"
    assert payment_status("", "XX") is None
    assert days_past_due("03") == 90 and days_past_due("00") == 0 and days_past_due("XX") is None


def test_loan_purpose_enum_incl_U():
    assert [loan_purpose(c) for c in ("P", "C", "R", "U", "")] == \
           ["PURCHASE", "CASHOUT", "REFI", "REFI", None]


def test_loan_type_from_amortization():
    assert [loan_type(c) for c in ("FRM", "ARM", "")] == ["FIXED", "ARM", None]


def test_normalize_real_first_row_maps_and_flags_nulls():
    with open("sf-loan-performance-data-sample.csv") as f:
        canon = normalize_row(parse_line(next(f)))
    assert canon["loan_id"] == "100023020488"
    assert canon["interest_rate"] == Decimal("5.375")
    assert canon["origination_date"] == date(2009, 8, 1)
    assert canon["maturity_date"] == date(2029, 9, 1)
    assert canon["borrower_state"] == "OH"
    assert canon["credit_grade"] == "B"
    assert canon["loan_purpose"] == "CASHOUT"
    assert canon["loan_type"] == "FIXED"                 # from Amortization Type FRM (field 35)
    assert canon["original_principal"] == Decimal("55000.00")
    assert canon["row_uid"] == "100023020488|082009"
    assert canon["source_system"] == "FNMA_SF_LPD"
    # no-source fields are null and surfaced as partial, not crashes
    assert canon["borrower_id"] is None and canon["document_status"] is None
    assert set(canon["_partial"]) >= {"borrower_id", "income_band", "document_status"}
    assert is_failed(canon) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/fnma_sf/test_normalize.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fnma_sf.normalize'`

- [ ] **Step 3: Write minimal implementation**

```python
# fnma_sf/normalize.py
from __future__ import annotations
from datetime import date
from decimal import Decimal, InvalidOperation

NO_SOURCE = ("borrower_id", "income_band", "document_status")
# Glossary field 27 enum verified against the CRT glossary: P=Purchase, C=Cash-Out
# Refinance, R=Refinance, U=Refinance-Not Specified (U folds into REFI).
_PURPOSE = {"P": "PURCHASE", "C": "CASHOUT", "R": "REFI", "U": "REFI"}
# Glossary field 35 Amortization Type: FRM=Fixed Rate, ARM=Adjustable Rate.
_AMORT = {"FRM": "FIXED", "ARM": "ARM"}


def mmyyyy(s):
    if not s or len(s) != 6 or not s.isdigit():
        return None
    mm, yyyy = int(s[:2]), int(s[2:])
    if not 1 <= mm <= 12:
        return None
    return date(yyyy, mm, 1)


def to_decimal(s):
    if s in (None, ""):
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def credit_grade(fico):
    if not fico or not fico.isdigit():
        return None
    f = int(fico)
    return "A" if f >= 740 else "B" if f >= 680 else "C" if f >= 620 else "D"


def payment_status(zero_bal, delinq):
    if zero_bal:                       # any zero-balance code -> loan closed
        return "CLOSED"
    if delinq == "00":
        return "CURRENT"
    if delinq.isdigit() and int(delinq) > 0:
        return "DELINQUENT"
    return None                        # "XX"/blank -> unknown


def days_past_due(delinq):
    # FNMA field 40 is a MONTH count ("00","01",…,"XX"); we approximate days as months*30.
    # This is an approximation, not literal days — documented so downstream reads it right.
    return int(delinq) * 30 if delinq.isdigit() else None


def loan_purpose(code):
    return _PURPOSE.get(code) if code else None


def loan_type(code):
    return _AMORT.get(code) if code else None


def _to_int(s):
    return int(s) if s and s.lstrip("-").isdigit() else None


def normalize_row(raw: dict) -> dict:
    period = raw["reporting_period"]
    canon = {
        "loan_id": raw["loan_id"] or None,
        "reporting_period": mmyyyy(period),
        "servicer_name": raw["servicer_name"] or None,
        "interest_rate": to_decimal(raw["interest_rate"]),
        "original_principal": to_decimal(raw["original_principal"]),
        "current_balance": to_decimal(raw["current_balance"]),
        "term_months": _to_int(raw["term_months"]),
        "origination_date": mmyyyy(raw["origination_date"]),
        "maturity_date": mmyyyy(raw["maturity_date"]),
        "borrower_state": raw["borrower_state"] or None,
        "loan_purpose": loan_purpose(raw["loan_purpose"]),
        "loan_type": loan_type(raw["amortization_type"]),
        "credit_grade": credit_grade(raw["credit_score"]),
        "payment_status": payment_status(raw["zero_balance_code"], raw["delinquency"]),
        "days_past_due": days_past_due(raw["delinquency"]),
        "last_payment_date": mmyyyy(raw["last_paid"]),
        "last_updated_at": mmyyyy(period),
        "source_system": "FNMA_SF_LPD",
        "profile": "sf_performance_panel",
        "row_uid": f"{raw['loan_id']}|{period}",
    }
    for f in NO_SOURCE:
        canon[f] = None
    canon["_partial"] = [f for f in NO_SOURCE if canon[f] is None]
    return canon


def is_failed(canon) -> bool:
    return canon["loan_id"] is None or canon["reporting_period"] is None \
        or canon["origination_date"] is None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/fnma_sf/test_normalize.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add fnma_sf/normalize.py fnma_sf/__init__.py tests/fnma_sf/test_normalize.py
git commit -m "feat(fnma_sf): null-safe normalization + FNMA derivations"
```

---

### Task 3: `panel.py` — Pass 1 structural checks (loan-month grain)

**Files:**
- Create: `fnma_sf/panel.py`
- Test: `tests/fnma_sf/test_panel.py`

**Interfaces:**
- Produces: `PanelFinding` (dataclass: `loan_id, reporting_period, kind, field, message`); `check_structure(rows: list[dict]) -> list[PanelFinding]` covering: duplicate `(loan_id, reporting_period)`; monthly **gaps** in a loan's period sequence; **static-field** drift across a loan's months (`origination_date, original_principal, term_months, maturity_date, borrower_state, credit_grade`); `current_balance` **increase** month-over-month (non-monotonic). Operates on normalized panel dicts.

- [ ] **Step 1: Write the failing test**

```python
# tests/fnma_sf/test_panel.py
from datetime import date
from decimal import Decimal
from fnma_sf.panel import check_structure


def _row(lid, period, **over):
    r = {"loan_id": lid, "reporting_period": period, "origination_date": date(2009, 8, 1),
         "original_principal": Decimal("100000"), "term_months": 240,
         "maturity_date": date(2029, 9, 1), "borrower_state": "OH", "credit_grade": "B",
         "current_balance": Decimal("90000")}
    r.update(over)
    return r


def test_clean_two_months_no_findings():
    rows = [_row("L", date(2009, 8, 1)), _row("L", date(2009, 9, 1), current_balance=Decimal("89000"))]
    assert check_structure(rows) == []


def test_duplicate_period_flagged():
    rows = [_row("L", date(2009, 8, 1)), _row("L", date(2009, 8, 1))]
    assert any(f.kind == "duplicate_period" for f in check_structure(rows))


def test_gap_in_months_flagged():
    rows = [_row("L", date(2009, 8, 1)), _row("L", date(2009, 11, 1))]
    assert any(f.kind == "period_gap" for f in check_structure(rows))


def test_static_field_drift_flagged():
    rows = [_row("L", date(2009, 8, 1)), _row("L", date(2009, 9, 1), original_principal=Decimal("999"))]
    assert any(f.kind == "static_drift" and f.field == "original_principal"
               for f in check_structure(rows))


def test_balance_increase_flagged():
    rows = [_row("L", date(2009, 8, 1), current_balance=Decimal("90000")),
            _row("L", date(2009, 9, 1), current_balance=Decimal("95000"))]
    assert any(f.kind == "balance_increase" for f in check_structure(rows))


def test_leading_zero_upb_not_flagged_as_increase():
    # A leading 0.00 UPB is "not reported yet" (confirmed in the sample), not a real
    # zero — the jump to the first real balance must NOT read as an increase.
    rows = [_row("L", date(2009, 8, 1), current_balance=Decimal("0.00")),
            _row("L", date(2009, 9, 1), current_balance=Decimal("54350.98"))]
    assert not any(f.kind == "balance_increase" for f in check_structure(rows))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/fnma_sf/test_panel.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fnma_sf.panel'`

- [ ] **Step 3: Write minimal implementation**

```python
# fnma_sf/panel.py
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass

STATIC = ("origination_date", "original_principal", "term_months",
          "maturity_date", "borrower_state", "credit_grade")


@dataclass
class PanelFinding:
    loan_id: str
    reporting_period: object
    kind: str
    field: str
    message: str


def _months(a, b):
    return (b.year - a.year) * 12 + (b.month - a.month)


def check_structure(rows: list[dict]) -> list[PanelFinding]:
    by_loan = defaultdict(list)
    for r in rows:
        by_loan[r["loan_id"]].append(r)
    out: list[PanelFinding] = []
    for lid, group in by_loan.items():
        periods = [r["reporting_period"] for r in group]
        seen = set()
        for p in periods:
            if p in seen:
                out.append(PanelFinding(lid, p, "duplicate_period", "reporting_period",
                                        f"{lid} has duplicate month {p}"))
            seen.add(p)
        ordered = sorted(group, key=lambda r: r["reporting_period"])
        for a, b in zip(ordered, ordered[1:]):
            if _months(a["reporting_period"], b["reporting_period"]) > 1:
                out.append(PanelFinding(lid, b["reporting_period"], "period_gap",
                                        "reporting_period", f"{lid} gap before {b['reporting_period']}"))
            # A leading 0.00 Current Actual UPB means "not reported yet", not a real zero
            # (confirmed: sample loans carry ~6 months of 0.00 before the first real UPB),
            # so only compare consecutive months where BOTH balances are > 0 — otherwise
            # the first real month reads as a spurious increase.
            ab, bb = a["current_balance"], b["current_balance"]
            if ab and bb and ab > 0 and bb > 0 and bb > ab:
                out.append(PanelFinding(lid, b["reporting_period"], "balance_increase",
                                        "current_balance", f"{lid} balance rose at {b['reporting_period']}"))
        first = ordered[0]
        for f in STATIC:
            if any(r.get(f) != first.get(f) for r in ordered):
                out.append(PanelFinding(lid, first["reporting_period"], "static_drift", f,
                                        f"{lid} static field {f} varies across months"))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/fnma_sf/test_panel.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add fnma_sf/panel.py tests/fnma_sf/test_panel.py
git commit -m "feat(fnma_sf): Pass 1 panel-consistency structural checks"
```

---

### Task 4: Panel row-local rule subset (reuse `loan_rules` by profile)

**Files:**
- Modify: `fnma_sf/panel.py`, `fnma_sf/__init__.py`
- Test: `tests/fnma_sf/test_panel.py`

**Interfaces:**
- Consumes: `loan_rules.load_rules`, `loan_rules.validate_dataset`, `loan_rules.Dataset`, `Rule.profiles`.
- Produces: `panel_row_rules() -> list[Rule]` (rules whose `profiles` include `"sf_performance_panel"` — the 8 row-local `ROW` rules); `validate_panel(rows) -> dict` returning `{"structural": list[PanelFinding], "row_local": list[Violation]}`. The row-local violations come from running the subset via `validate_dataset(Dataset(rows, [], []), panel_row_rules())` — identity/time rules are **absent** from the subset, so they never misfire at panel grain.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/fnma_sf/test_panel.py
from decimal import Decimal
from datetime import date
from fnma_sf.panel import panel_row_rules, validate_panel


def test_subset_excludes_identity_and_time_rules():
    ids = {r.id for r in panel_row_rules()}
    assert "duplicate_loan_id" not in ids and "stale_record" not in ids
    assert "required_fields" not in ids and "document_status_present" not in ids
    assert {"valid_dates", "non_negative_amounts", "interest_rate_range",
            "balance_le_principal", "closed_with_balance", "maturity_after_origination",
            "payment_status_vs_dpd", "valid_state_code"} <= ids


def test_row_local_rule_flags_bad_rate_on_a_panel_row():
    row = {"row_uid": "L|082009", "loan_id": "L", "reporting_period": date(2009, 8, 1),
           "origination_date": date(2009, 8, 1), "maturity_date": date(2029, 9, 1),
           "original_principal": Decimal("100000"), "current_balance": Decimal("90000"),
           "interest_rate": Decimal("99.0"), "borrower_state": "OH",
           "payment_status": "CURRENT", "days_past_due": 0}
    res = validate_panel([row])
    assert any(v.rule_id == "interest_rate_range" for v in res["row_local"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/fnma_sf/test_panel.py -v`
Expected: FAIL — `ImportError: cannot import name 'panel_row_rules'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to fnma_sf/panel.py
from loan_rules import load_rules, validate_dataset, Dataset

PANEL_PROFILE = "sf_performance_panel"


def panel_row_rules():
    return [r for r in load_rules(None) if PANEL_PROFILE in r.profiles]


def validate_panel(rows: list[dict]) -> dict:
    return {
        "structural": check_structure(rows),
        "row_local": validate_dataset(Dataset(rows, [], []), panel_row_rules()),
    }
```

Add to `fnma_sf/__init__.py`:

```python
from fnma_sf.normalize import normalize_row, is_failed
from fnma_sf.panel import validate_panel, panel_row_rules
__all__ += ["normalize_row", "is_failed", "validate_panel", "panel_row_rules"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/fnma_sf/test_panel.py -v`
Expected: PASS (structural + subset + row-local)

- [ ] **Step 5: Commit**

```bash
git add fnma_sf/panel.py fnma_sf/__init__.py tests/fnma_sf/test_panel.py
git commit -m "feat(fnma_sf): panel row-local rule subset via loan_rules profiles"
```

---

### Task 5: `collapse.py` — Pass 2 (latest month per loan)

**Files:**
- Create: `fnma_sf/collapse.py`
- Test: `tests/fnma_sf/test_collapse.py`

**Interfaces:**
- Produces: `collapse_latest(rows: list[dict]) -> list[dict]` — group by `loan_id`, keep the row with the max `reporting_period`, and return **loan-tape-grain** dicts (drop panel-only keys; set `row_uid = loan_id` so the loan-grain rules key uniquely). Deterministic order (sorted by `loan_id`).

- [ ] **Step 1: Write the failing test**

```python
# tests/fnma_sf/test_collapse.py
from datetime import date
from decimal import Decimal
from fnma_sf.parse import iter_rows
from fnma_sf.normalize import normalize_row
from fnma_sf.collapse import collapse_latest


def _r(lid, period, bal):
    return {"loan_id": lid, "reporting_period": period, "current_balance": bal,
            "payment_status": "CURRENT", "row_uid": f"{lid}|x"}


def test_keeps_latest_period_per_loan():
    rows = [_r("L", date(2009, 8, 1), Decimal("90000")),
            _r("L", date(2010, 1, 1), Decimal("50000"))]
    out = collapse_latest(rows)
    assert len(out) == 1
    assert out[0]["current_balance"] == Decimal("50000")   # latest month wins
    assert out[0]["row_uid"] == "L"                          # loan-grain key


def test_sample_collapses_to_eight_loans():
    rows = [normalize_row(r) for r in iter_rows("sf-loan-performance-data-sample.csv")]
    out = collapse_latest(rows)
    assert len(out) == 8
    for loan in out:
        same = [r for r in rows if r["loan_id"] == loan["loan_id"]]
        assert loan["last_updated_at"] == max(r["reporting_period"] for r in same)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/fnma_sf/test_collapse.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fnma_sf.collapse'`

- [ ] **Step 3: Write minimal implementation**

```python
# fnma_sf/collapse.py
from __future__ import annotations
from collections import defaultdict

_DROP = ("reporting_period", "_partial", "profile")


def collapse_latest(rows: list[dict]) -> list[dict]:
    by_loan = defaultdict(list)
    for r in rows:
        by_loan[r["loan_id"]].append(r)
    out = []
    for lid in sorted(by_loan):
        latest = max(by_loan[lid], key=lambda r: r["reporting_period"])
        loan = {k: v for k, v in latest.items() if k not in _DROP}
        loan["row_uid"] = lid                    # loan-grain unique key
        out.append(loan)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/fnma_sf/test_collapse.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add fnma_sf/collapse.py tests/fnma_sf/test_collapse.py
git commit -m "feat(fnma_sf): Pass 2 collapse to latest month per loan"
```

---

### Task 6: `pipeline.py` — Pass 3 orchestration (run the unchanged 15 rules)

**Files:**
- Create: `fnma_sf/pipeline.py`
- Modify: `fnma_sf/__init__.py`
- Test: `tests/fnma_sf/test_pipeline.py`

**Interfaces:**
- Consumes: `validate_panel`, `collapse_latest`, `loan_rules.load_rules`/`validate_dataset`/`Dataset`.
- Produces: `FNMA_PASS3_SKIP` (the two absence-flagging rules this source can't feed); `pass3_rules() -> list[Rule]` (the 13 applicable rules); `ingest_panel(rows: list[dict]) -> dict` returning `{"panel": {structural, row_local}, "loan_tape": list[dict], "loan_exceptions": list[Violation], "failed": list[dict]}`. Pass 3 runs `pass3_rules()` on `Dataset(loan_tape, [], [])` — the 15 rules **unchanged**, minus the 2 whose inputs the FNMA source structurally lacks (field-availability gating, same principle as Pass 1's `profiles` filter). Failed rows (`is_failed`) are separated, not fed downstream.

- [ ] **Step 1: Write the failing test**

```python
# tests/fnma_sf/test_pipeline.py
from fnma_sf.parse import iter_rows
from fnma_sf.normalize import normalize_row
from fnma_sf.pipeline import ingest_panel


def test_end_to_end_on_sample_no_null_field_floods():
    rows = [normalize_row(r) for r in iter_rows("sf-loan-performance-data-sample.csv")]
    res = ingest_panel(rows)
    assert len(res["loan_tape"]) == 8                 # collapsed
    assert res["failed"] == []                        # sample rows all parse
    assert isinstance(res["loan_exceptions"], list)   # ran; no oracle on real data
    flagged = {v.rule_id for v in res["loan_exceptions"]}
    # the four null-field artifacts must NOT appear (borrower_id / document_status absent):
    #   - required_fields, document_status_present are Pass-3-skipped for this source
    #   - suspicious_borrower_repeat, duplicate_borrower_combo are null-guarded in loan_rules
    assert flagged.isdisjoint({"required_fields", "document_status_present",
                               "suspicious_borrower_repeat", "duplicate_borrower_combo"})
    # (stale_record MAY flag all 8 — the sample is 2009–2020 vintage vs the rule's
    #  as_of; that's an honest finding, not a null-field artifact, so it's allowed.)


def test_failed_rows_are_separated_not_crashing():
    rows = [normalize_row({"loan_id": "", "reporting_period": "082009",
                           "servicer_name": "", "interest_rate": "", "original_principal": "",
                           "current_balance": "", "term_months": "", "origination_date": "082009",
                           "maturity_date": "", "borrower_state": "", "loan_purpose": "",
                           "credit_score": "", "zero_balance_code": "", "delinquency": "00",
                           "last_paid": ""})]
    res = ingest_panel(rows)
    assert len(res["failed"]) == 1 and res["loan_tape"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/fnma_sf/test_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fnma_sf.pipeline'`

- [ ] **Step 3: Write minimal implementation**

```python
# fnma_sf/pipeline.py
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
```

Add to `fnma_sf/__init__.py`:

```python
from fnma_sf.collapse import collapse_latest
from fnma_sf.pipeline import ingest_panel
__all__ += ["collapse_latest", "ingest_panel"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/fnma_sf/test_pipeline.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add fnma_sf/pipeline.py fnma_sf/__init__.py tests/fnma_sf/test_pipeline.py
git commit -m "feat(fnma_sf): Pass 3 orchestration over the unchanged 15 loan-grain rules"
```

---

### Task 7: Streaming demo-slice builder + committed fixture + Makefile target

**Files:**
- Modify: `fnma_sf/pipeline.py`, `fnma_sf/__init__.py`, `Makefile`
- Create: `tests/fnma_sf/fixtures/collapsed_sample.csv` (generated once, committed)
- Test: `tests/fnma_sf/test_pipeline.py`

**Interfaces:**
- Produces: `build_demo_tape(src_path, out_csv, n_loans=5000) -> int` — **streams** the (2.58M-row) source once, keeping only the **first `n_loans` distinct** `loan_id`s and, for each, its latest-period row (O(n_loans) memory); normalizes, collapses, and writes a `loan_tape` CSV via `data._serialize.write_loans_csv` (canonical 21 columns). Returns the loan count. `make fnma-demo` builds a 5,000-loan tape from `2025Q1.csv`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/fnma_sf/test_pipeline.py
import csv
from fnma_sf.pipeline import build_demo_tape
from data._serialize import CANONICAL_COLUMNS


def test_build_demo_tape_streams_and_collapses(tmp_path):
    out = tmp_path / "loan_tape.csv"
    n = build_demo_tape("sf-loan-performance-data-sample.csv", str(out), n_loans=8)
    assert n == 8
    with open(out) as f:
        reader = csv.reader(f)
        header = next(reader)
        body = list(reader)
    assert header == CANONICAL_COLUMNS           # canonical 21 cols, no row_uid leaked
    assert len(body) == 8                        # collapsed to 8 loans


def test_build_demo_tape_caps_distinct_loans(tmp_path):
    out = tmp_path / "t.csv"
    assert build_demo_tape("sf-loan-performance-data-sample.csv", str(out), n_loans=3) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/fnma_sf/test_pipeline.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_demo_tape'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to fnma_sf/pipeline.py
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
```

Add `build_demo_tape` to `fnma_sf/__init__.py` `__all__`. Add to `Makefile`:

```makefile
fnma-demo:
	python -c "from fnma_sf import build_demo_tape; print(build_demo_tape('2025Q1.csv', 'data/fnma_loan_tape.csv', 5000))"
```

- [ ] **Step 4: Run test + build the committed fixture**

Run: `pytest tests/fnma_sf/test_pipeline.py -v`
Then build the small committed fixture from the sample (NOT from 2025Q1):
`python -c "from fnma_sf import build_demo_tape; build_demo_tape('sf-loan-performance-data-sample.csv', 'tests/fnma_sf/fixtures/collapsed_sample.csv', 8)"`
Expected: tests PASS; `collapsed_sample.csv` (8 rows, canonical header) created.

- [ ] **Step 5: Commit**

```bash
git add fnma_sf/pipeline.py fnma_sf/__init__.py Makefile tests/fnma_sf/test_pipeline.py tests/fnma_sf/fixtures/collapsed_sample.csv
git commit -m "feat(fnma_sf): streaming demo-slice builder + committed collapsed fixture"
```

---

### Task 8: Import-purity guard for `fnma_sf`

**Files:**
- Create: `tests/fnma_sf/test_import_purity.py`

**Interfaces:** a test proving `fnma_sf` (and its submodules) drag in no Mongo/app modules — mirrors the generator's `test_import_purity`. `fnma_sf` may import `loan_rules` and `data` (both pure); it must not import `motor`/`beanie`/`pymongo`/`fastapi`/`backend`.

- [ ] **Step 1: Write the failing test**

```python
# tests/fnma_sf/test_import_purity.py
import subprocess
import sys


def test_fnma_sf_is_import_pure():
    code = (
        "import sys, fnma_sf, fnma_sf.parse, fnma_sf.normalize, fnma_sf.panel,"
        " fnma_sf.collapse, fnma_sf.pipeline;"
        "bad=[m for m in set(sys.modules) if m.split('.')[0] in "
        "{'motor','beanie','pymongo','fastapi','backend'}];"
        "assert not bad, bad; print('ok')"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "ok" in r.stdout
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `pytest tests/fnma_sf/test_import_purity.py -v`
Expected: PASS if the package is pure. If it FAILS, a submodule leaked a Mongo/app import — fix that module (the connector must import only `loan_rules`, `data`, and stdlib).

- [ ] **Step 3: (only if the test failed) remove the offending import**

No new code if already pure; otherwise relocate the impure import out of the module chain.

- [ ] **Step 4: Run the full suite**

Run: `pytest -q`
Expected: entire `fnma_sf` suite green.

- [ ] **Step 5: Commit**

```bash
git add tests/fnma_sf/test_import_purity.py
git commit -m "test(fnma_sf): import-purity guard (no Mongo/app leakage)"
```

---

## Self-Review

**1. Spec coverage** (parent §6.1–6.3, §7, §12.2):
- §6.1 source profiles / grain → `normalize_row` sets `profile="sf_performance_panel"`; collapsed tape is `loan_tape`-grain (Task 2, 5). ✓
- §6.2 Pass 1 (structural + row-local subset) → Tasks 3, 4; Pass 2 collapse-latest → Task 5; Pass 3 unchanged 15 rules → Task 6. ✓
- §6.3 connector field map incl. leading-pipe indexing, MMYYYY, U-purpose, XX-delinquency, null no-source fields → Tasks 1, 2. ✓
- §7 profiles subset (8 row-local rules; identity/time excluded) → Task 4 (`panel_row_rules`). ✓
- §12.2 5,000-loan demo slice streamed from `2025Q1.csv`; raw files git-ignored; small collapsed fixture committed → Task 7. ✓
- `loan_type` from Amortization Type (field 35, FRM→FIXED/ARM→ARM) → Tasks 1, 2 (was dropped; now mapped). ✓
- Import purity (no Mongo/app leakage) → Task 8. ✓

**Review-round fixes (3rd pass):**
- **HIGH — null-field Pass 3 floods:** `borrower_id` is uniformly null on FNMA, which turned `suspicious_borrower_repeat`/`duplicate_borrower_combo` (null-collapsing counter) and `required_fields`/`document_status_present` (absence-flagging) into 100%-flag artifacts. Fixed two ways: (a) `loan_rules` null-guards the two borrower-counter checks (universal correctness); (b) `pass3_rules()` skips the two absence-flaggers for this source. Verified: `{None: 8} > 3` would have flagged all 8. ✓
- **MEDIUM — `loan_type` dropped:** now mapped from field 35 (confirmed `FRM` in the sample). ✓
- **MEDIUM — 0.00 UPB monotonicity misfire:** confirmed 6 leading `0.00` months before the first real balance; Pass 1 now compares only months where both balances > 0. ✓
- **LOW:** purpose enum P/C/R/U verified against the glossary; `×30` dpd documented; row-count test made newline-robust; import-purity guard added. ✓

**2. Placeholder scan:** no `TBD`/`TODO`/"handle edge cases"; every code step is concrete. The one intentional "no specific counts" assertion in Task 6 is deliberate — real data has no ground truth, stated in Global Constraints.

**3. Type/name consistency:** `parse_line` keys (Task 1) are consumed by `normalize_row` (Task 2); `normalize_row` output keys (`reporting_period`, `current_balance`, `row_uid`, `_partial`) are consumed by `panel`/`collapse`/`pipeline` (Tasks 3–7); `panel_row_rules`/`validate_panel`/`collapse_latest`/`ingest_panel`/`build_demo_tape` signatures match across producer and test tasks; reuse of `loan_rules` (`load_rules`, `validate_dataset`, `Dataset`, `Rule.profiles`) and `data._serialize` (`CANONICAL_COLUMNS`, `write_loans_csv`) matches those packages' interfaces from the generator plan.

---

## Notes for the executor

- **Sequencing:** do not start until the generator plan is green — this plan imports `loan_rules` and `data._serialize` from it.
- **No oracle:** never assert exception counts on real data. Assert mapping/structural facts against the 8-loan sample and hand-built fixtures only.
- **Pass 3 rule set on FNMA:** `pass3_rules()` runs 13 of the 15 rules — it skips `required_fields` and `document_status_present`, whose inputs (`borrower_id`; `document_status`/manifest) the FNMA source structurally lacks and which flag on *absence* (they'd flag every loan). Those absences are surfaced by `normalize_row`'s partial-import instead. The borrower-counter rules (`suspicious_borrower_repeat`, `duplicate_borrower_combo`) are null-guarded in `loan_rules`, so they no-op here. `source_conflict` no-ops with no servicer_update. The rules themselves stay unchanged and strict on the graded synthetic tape.
- **Expected (honest) Pass 3 findings:** `stale_record` may flag old-vintage loans relative to its `as_of` (true of the 2009–2020 sample; on the 2025 demo file it won't). These are real, reviewer-gated findings — not null-field artifacts — so leave them.
- **`backend/app/ingestion/` adapter** (wiring this connector to an upload endpoint + Mongo) is out of scope here; this package stays pure and DB-free.
