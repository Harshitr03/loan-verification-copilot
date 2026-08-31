# Synthetic Data Generator + `loan_rules` Spine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the standalone `loan_rules` package (self-describing `Rule` objects carrying both `check` and `corrupt`) and a seeded generator that emits the synthetic organizer data package with a machine-verifiable ground-truth oracle.

**Architecture:** One `Rule` object per validation concern carries a pure `check` (detect) and a pure `corrupt` (manufacture), both taking `params` explicitly — so injection and detection can never drift. The generator builds ~5,000 internally-consistent clean loans, then drives the rules' `corrupt` to inject defects, emitting a ground-truth bundle for every implicated loan. A minimal rule runner re-runs `check` over the result to prove the oracle end-to-end.

**Tech Stack:** Python 3.12, numpy (≥1.25, for `Generator.spawn`), Faker, bcrypt, pytest. Loans are plain `dict`s of normalized Python values (dates as `datetime.date`, money as `Decimal`, ints as `int`); a corruption may replace a value with a raw invalid one (e.g. an unparseable date string). No pandas/Mongo/FastAPI in `loan_rules` — it stays import-pure.

**Spec:** `docs/specs/2026-08-29-data-generator-design.md` (parent: `docs/specs/2026-08-27-loan-verification-copilot-design.md`)

## Global Constraints

- **Python 3.12**; `loan_rules` is a **standalone top-level package**, NOT under `backend/app/`, editable-installed via root `pyproject.toml`. Its `__init__` chain imports nothing but rule definitions and factories (no Beanie/Motor/config, no `tests`).
- **`check`/`corrupt` are pure functions taking `params` explicitly** — no closure over params. `params` is a read-only `Mapping` stored once on `Rule.params`.
- **Surrogate key `row_uid`.** Every loan carries an immutable `row_uid: str` assigned at clean-build time, **before any corruption**, and never mutated (unlike `loan_id`, which rules like `required_fields`/`duplicate_loan_id` deliberately change). `row_uid` is the **primary key** of every `Bundle` and `Violation`, and the join key of the oracle. `loan_id` is demoted to ordinary data. `row_uid` is an internal surrogate: it is written to `ground_truth_exceptions.csv` (our oracle) but **not** to `loan_tape.csv` (the 21 canonical columns only).
- **Two RNGs, both seeded from `--seed`:** one `numpy.random.Generator` (per-rule `spawn` sub-streams) for numeric/date/choice draws; `Faker.seed_instance(seed)` separately (Faker does NOT use numpy's RNG).
- **Byte-reproducibility requires stable serialization:** money via `Decimal` quantized to 2dp then `str()`; fixed CSV column order; `csv.writer(lineterminator="\n")`; `json.dump(..., sort_keys=True, indent=2)`. `users.json` is EXCLUDED from reproducibility hashing (bcrypt salts are random).
- **The defective set ≡ the set of `row_uid`s in `ground_truth_exceptions.csv`.** Every rule's `corrupt` emits a bundle for **every** loan it implicates, including an unmutated partner (whose `observed_value == original_value`).
- **Only enabled rules are injected and checked** (`enabled` flag in `validation_rules.json`); `load_rules` returns only enabled, params-bound rules.
- **Bundle/Violation shape:** `{row_uid, loan_id, rule_id, field, observed_value, expected, sibling_value?, message}`. `Bundle` adds an oracle-only `original_value`. There is **no** `corrupted_value` field anywhere.
- **21 canonical fields (parent §4):** `loan_id, borrower_id, loan_type, origination_date, maturity_date, original_principal, current_balance, interest_rate, term_months, borrower_state, loan_purpose, credit_grade, employment_length, income_band, payment_status, days_past_due, servicer_name, last_payment_date, last_updated_at, document_status, source_system`.
- **Defect ordering & pools:** DATASET corruptions run **first** on the clean tape (in the safe order `source_conflict → document_status_present → duplicate_borrower_combo → suspicious_borrower_repeat → duplicate_loan_id`, so `loan_id`-mutating rules run last); the loans they implicate are then **excluded** from the ROW-corruption pool. ROW corruptions target ~`defect_rate × n` distinct loans, ≤2 defects each, per-type target ~35.
- **DATASET↔DATASET isolation (`avoid` set):** the checks join on `loan_id` (what the real files/engine key on), yet `duplicate_loan_id` mutates `loan_id`. So every DATASET `corrupt` that *selects an existing row* (`source_conflict`, `document_status_present`, `duplicate_borrower_combo`, `duplicate_loan_id`) takes an `avoid: set[str]` of `row_uid`s it must not target. The generator threads the running union of all already-implicated `row_uid`s (plus each rule's own within-loop picks) into `avoid`, so an identity-mutating rule never re-picks a prior partner (kills the collision-dissolution bug) and never touches a loan another cross-file rule already joined on (kills the orphaned-join bug). `suspicious_borrower_repeat` appends fresh rows and ignores `avoid`.
- **`profiles` (parent §6.1/§7):** `Rule.profiles: frozenset[str]` defaults to `{"loan_tape"}`. The 8 row-local rules (`valid_dates`, `maturity_after_origination`, `non_negative_amounts`, `balance_le_principal`, `interest_rate_range`, `payment_status_vs_dpd`, `closed_with_balance`, `valid_state_code`) pass `profiles=BOTH` (`frozenset({"loan_tape", "sf_performance_panel"})`); the 7 identity/time rules (incl. `required_fields`, `stale_record`) keep the default. The generator only produces the `loan_tape` profile, so it drives all 15 rules; `profiles` is consumed later by the panel-consistency pass, not by generation.

---

## File Structure

```
pyproject.toml                       # editable install of loan_rules; deps; pytest config
loan_rules/
  __init__.py                        # exports the public API
  base.py                            # Scope, Rule, Bundle, Violation, Dataset, factories
  context.py                         # build_context, validate_dataset (the runner)
  registry.py                        # ALL_RULES, register, load_rules, write_default_rules_json
  rules_row.py                       # the 10 ROW-scope rules
  rules_dataset.py                   # the 5 DATASET-scope rules
  _dates.py                          # parse_date helper
tests/loan_rules/
  helpers.py                         # make_clean_loan, make_clean_dataset
  test_base.py                       # Rule hashability/immutability; factories
  test_registry.py                   # params binding + enabled filtering
  test_rules_row.py                  # parametrized ROW round-trip + per-rule edges
  test_rules_dataset.py              # parametrized DATASET round-trip + per-rule edges
  test_runner.py                     # validate_dataset dispatch
  test_import_purity.py              # loan_rules imports no app/db/tests
data/
  __init__.py
  generate.py                        # build_package + generate + CLI
  _clean.py                          # correlated clean builders (assigns row_uid)
  _allocate.py                       # ROW defect allocation
  _serialize.py                      # stable CSV/JSON writers
tests/data/
  test_clean.py                      # clean rows pass all rules
  test_allocate.py                   # allocation feasibility + share
  test_serialize.py                  # deterministic serialization
  test_generate.py                   # reproducibility + superset oracle
Makefile                             # seed / test / install
```

---

### Task 1: Project scaffolding + core types + factories

**Files:**
- Create: `pyproject.toml`, `loan_rules/__init__.py`, `loan_rules/base.py`
- Test: `tests/loan_rules/test_base.py`

**Interfaces:**
- Produces: `Scope` (enum `ROW`/`DATASET`); `Rule` (frozen dataclass `id:str, scope:Scope, severity:str, params:Mapping, message_tmpl:str, check:Callable, corrupt:Callable, profiles:frozenset=frozenset({"loan_tape"})` — **every field except `id` is `compare=False`**, so `Rule` hashes/eqs by `id` alone and stays hashable despite the `MappingProxyType` params; `profiles` (parent §6.1/§7) is last with a `loan_tape` default so the 7 identity/time rules need no override and the 8 row-local rules pass `profiles=BOTH`); `Bundle` (`row_uid, loan_id, rule_id, field, observed_value, expected, message, sibling_value=None, original_value=None`); `Violation` (`row_uid, loan_id, rule_id, field, observed_value, expected, message, severity, sibling_value=None`); `Dataset` (`loans:list[dict], servicer_updates:list[dict], manifest:list[dict]`); factories `bundle_from(loan, rule_id, field, observed, expected, message, sibling=None, original=None) -> Bundle` and `violation_from(loan, rule_id, field, observed, expected, message, severity="medium", sibling=None) -> Violation` (both read `loan["row_uid"]` and `loan.get("loan_id","")`); type alias `Loan = dict[str, Any]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/loan_rules/test_base.py
from types import MappingProxyType
import dataclasses
import pytest
from loan_rules.base import Scope, Rule, Bundle, Violation, bundle_from, violation_from


def _c(loan, params): return None
def _x(loan, rng, params): return loan, None


def make_rule(rid="r"):
    return Rule(id=rid, scope=Scope.ROW, severity="low",
                params=MappingProxyType({"a": 1}), message_tmpl="{field}",
                check=_c, corrupt=_x)


def test_rule_is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        make_rule().id = "x"


def test_rule_is_hashable_and_eq_by_id():
    assert {make_rule(), make_rule()} == {make_rule()}     # hashable; equal by id
    assert make_rule("a") != make_rule("b")


def test_params_is_readonly_mapping():
    with pytest.raises(TypeError):
        make_rule().params["a"] = 99


def test_factories_read_row_uid_and_loan_id():
    loan = {"row_uid": "U1", "loan_id": "LN1"}
    b = bundle_from(loan, "r", "f", 1, 2, "m", original=0)
    v = violation_from(loan, "r", "f", 1, 2, "m", severity="high")
    assert (b.row_uid, b.loan_id, b.original_value) == ("U1", "LN1", 0)
    assert (v.row_uid, v.loan_id, v.severity) == ("U1", "LN1", "high")


def test_rule_profiles_default_is_loan_tape():
    assert make_rule().profiles == frozenset({"loan_tape"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/loan_rules/test_base.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'loan_rules'`

- [ ] **Step 3: Write minimal implementation**

```toml
# pyproject.toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "loan-verification-copilot"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["numpy>=1.25", "faker>=24", "bcrypt>=4"]

[project.optional-dependencies]
dev = ["pytest>=8"]

[tool.setuptools]
packages = ["loan_rules"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

```python
# loan_rules/base.py
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping, Optional

Loan = dict[str, Any]


class Scope(Enum):
    ROW = "row"
    DATASET = "dataset"


@dataclass(frozen=True)
class Rule:
    id: str
    scope: Scope = field(compare=False)
    severity: str = field(compare=False)
    params: Mapping = field(compare=False)
    message_tmpl: str = field(compare=False)
    check: Callable = field(compare=False)
    corrupt: Callable = field(compare=False)
    # profiles: dataset profiles this rule applies to (parent spec §6.1/§7).
    # Defaults to loan_tape (the graded path); the 8 row-local rules override to BOTH.
    profiles: frozenset = field(default=frozenset({"loan_tape"}), compare=False)


@dataclass
class Bundle:
    row_uid: str
    loan_id: str
    rule_id: str
    field: str
    observed_value: Any
    expected: Any
    message: str
    sibling_value: Optional[Any] = None
    original_value: Optional[Any] = None  # oracle-only


@dataclass
class Violation:
    row_uid: str
    loan_id: str
    rule_id: str
    field: str
    observed_value: Any
    expected: Any
    message: str
    severity: str
    sibling_value: Optional[Any] = None


@dataclass
class Dataset:
    loans: list[Loan]
    servicer_updates: list[dict]
    manifest: list[dict]


def bundle_from(loan, rule_id, field, observed, expected, message, sibling=None, original=None):
    return Bundle(loan.get("row_uid"), loan.get("loan_id", ""), rule_id, field,
                  observed, expected, message, sibling, original)


def violation_from(loan, rule_id, field, observed, expected, message, severity="medium", sibling=None):
    return Violation(loan.get("row_uid"), loan.get("loan_id", ""), rule_id, field,
                     observed, expected, message, severity, sibling)
```

```python
# loan_rules/__init__.py
from loan_rules.base import (Scope, Rule, Bundle, Violation, Dataset, Loan,
                             bundle_from, violation_from)

__all__ = ["Scope", "Rule", "Bundle", "Violation", "Dataset", "Loan",
           "bundle_from", "violation_from"]
```

Note: `@dataclass(frozen=True)` with a positional field marked `compare=False` still requires it be declared without a default before the callables — here all non-`id` fields carry `field(compare=False)` with no default, which is legal because none of them uses a value-default. `id` keeps its implicit compare/hash role.

- [ ] **Step 4: Install editable + run test to verify it passes**

Run: `pip install -e ".[dev]" && pytest tests/loan_rules/test_base.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml loan_rules/ tests/loan_rules/test_base.py
git commit -m "feat(loan_rules): core types (row_uid-keyed) + factories + editable package"
```

---

### Task 2: Params registry — `load_rules`, `write_default_rules_json`, enabled filtering

**Files:**
- Create: `loan_rules/registry.py`
- Modify: `loan_rules/__init__.py`
- Test: `tests/loan_rules/test_registry.py`

**Interfaces:**
- Consumes: `Rule`, `Scope` (Task 1).
- Produces: `ALL_RULES: list[Rule]` (grows as `rules_row`/`rules_dataset` import and call `register`); `register(rule) -> Rule`; `load_rules(path: str | None = None) -> list[Rule]` (returns only **enabled** rules, params overlaid from JSON, defaults otherwise); `write_default_rules_json(path) -> None` (dumps `{id: {**default_params, "enabled": True, "severity": severity}}`, sorted).

- [ ] **Step 1: Write the failing test**

```python
# tests/loan_rules/test_registry.py
import json
from types import MappingProxyType
from loan_rules.base import Rule, Scope
from loan_rules import registry


def _c(loan, params): return None
def _x(loan, rng, params): return loan, None


def _fake():
    return [
        Rule("demo", Scope.ROW, "low", MappingProxyType({"threshold": 10}), "{field}", _c, _x),
        Rule("off", Scope.ROW, "high", MappingProxyType({}), "{field}", _c, _x),
    ]


def test_write_then_load_binds_and_filters(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "ALL_RULES", _fake())
    p = tmp_path / "validation_rules.json"
    registry.write_default_rules_json(str(p))
    doc = json.loads(p.read_text())
    assert doc["demo"]["threshold"] == 10 and doc["demo"]["enabled"] is True
    doc["demo"]["threshold"] = 99
    doc["off"]["enabled"] = False
    p.write_text(json.dumps(doc))
    rules = registry.load_rules(str(p))
    assert {r.id for r in rules} == {"demo"}
    assert dict(rules[0].params)["threshold"] == 99


def test_load_without_file_uses_defaults(monkeypatch):
    monkeypatch.setattr(registry, "ALL_RULES", _fake())
    assert {r.id for r in registry.load_rules(None)} == {"demo", "off"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/loan_rules/test_registry.py -v`
Expected: FAIL — `AttributeError: module 'loan_rules.registry' has no attribute 'ALL_RULES'`

- [ ] **Step 3: Write minimal implementation**

```python
# loan_rules/registry.py
from __future__ import annotations
import dataclasses
import json
from types import MappingProxyType
from loan_rules.base import Rule

ALL_RULES: list[Rule] = []


def register(rule: Rule) -> Rule:
    ALL_RULES.append(rule)
    return rule


def write_default_rules_json(path: str) -> None:
    doc = {r.id: {**dict(r.params), "enabled": True, "severity": r.severity} for r in ALL_RULES}
    with open(path, "w") as f:
        json.dump(doc, f, sort_keys=True, indent=2)


def load_rules(path: str | None = None) -> list[Rule]:
    overrides = {}
    if path is not None:
        with open(path) as f:
            overrides = json.load(f)
    out: list[Rule] = []
    for r in ALL_RULES:
        cfg = overrides.get(r.id, {})
        if cfg.get("enabled", True) is False:
            continue
        merged = {**dict(r.params),
                  **{k: v for k, v in cfg.items() if k not in ("enabled", "severity")}}
        out.append(dataclasses.replace(r, params=MappingProxyType(merged),
                                       severity=cfg.get("severity", r.severity)))
    return out
```

Add to `loan_rules/__init__.py`:

```python
from loan_rules.registry import ALL_RULES, register, load_rules, write_default_rules_json
__all__ += ["ALL_RULES", "register", "load_rules", "write_default_rules_json"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/loan_rules/test_registry.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add loan_rules/registry.py loan_rules/__init__.py tests/loan_rules/test_registry.py
git commit -m "feat(loan_rules): params registry with default emit + enabled filtering"
```

---

### Task 3: ROW round-trip harness + `required_fields` + date helper

**Files:**
- Create: `loan_rules/_dates.py`, `loan_rules/rules_row.py`, `tests/loan_rules/helpers.py`
- Test: `tests/loan_rules/test_rules_row.py`

**Interfaces:**
- Consumes: `Rule`, `Scope`, `bundle_from`, `violation_from` (Task 1); `register` (Task 2).
- Produces: `make_clean_loan(**overrides) -> Loan` (a fully-valid loan **including `row_uid`**); ROW contract `check(loan, params) -> Violation | None`, `corrupt(loan, rng, params) -> (loan, Bundle)`; `parse_date(value) -> date | None`; first rule `required_fields`.

- [ ] **Step 1: Write the failing test**

```python
# tests/loan_rules/helpers.py
from datetime import date
from decimal import Decimal


def make_clean_loan(i=1, **overrides):
    loan = {
        "row_uid": f"U{i:05d}", "loan_id": f"LN{i:05d}", "borrower_id": f"BR{i:05d}",
        "loan_type": "FIXED", "origination_date": date(2020, 1, 15),
        "maturity_date": date(2050, 1, 15), "original_principal": Decimal("250000.00"),
        "current_balance": Decimal("200000.00"), "interest_rate": Decimal("5.25"),
        "term_months": 360, "borrower_state": "CA", "loan_purpose": "PURCHASE",
        "credit_grade": "A", "employment_length": 10, "income_band": "100K-150K",
        "payment_status": "CURRENT", "days_past_due": 0, "servicer_name": "Acme Servicing",
        "last_payment_date": date(2024, 6, 1), "last_updated_at": date(2024, 6, 15),
        "document_status": "COMPLETE", "source_system": "ORIG_SYS",
    }
    loan.update(overrides)
    return loan
```

```python
# tests/loan_rules/test_rules_row.py
import numpy as np
import pytest
from loan_rules.base import Scope
from loan_rules import registry
import loan_rules.rules_row  # noqa: F401  (registers rules)
from tests.loan_rules.helpers import make_clean_loan

ROW_RULES = [r for r in registry.ALL_RULES if r.scope == Scope.ROW]


def _rule(rid):
    return next(r for r in ROW_RULES if r.id == rid)


@pytest.mark.parametrize("rule", ROW_RULES, ids=lambda r: r.id)
def test_row_round_trip(rule):
    rng = np.random.default_rng(0)
    clean = make_clean_loan()
    assert rule.check(clean, rule.params) is None, "clean must pass"
    corrupted, bundle = rule.corrupt(make_clean_loan(), rng, rule.params)
    v = rule.check(corrupted, rule.params)
    assert v is not None, f"{rule.id}: injected defect not detected"
    assert v.field == bundle.field
    assert bundle.row_uid == corrupted["row_uid"]


def test_required_fields_edge_blank_borrower():
    assert _rule("required_fields").check(make_clean_loan(borrower_id=""), _rule("required_fields").params) is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/loan_rules/test_rules_row.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'loan_rules.rules_row'`

- [ ] **Step 3: Write minimal implementation**

```python
# loan_rules/_dates.py
from __future__ import annotations
from datetime import date, datetime

_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d")


def parse_date(value):
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    for fmt in _FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None
```

```python
# loan_rules/rules_row.py
from __future__ import annotations
from types import MappingProxyType
from loan_rules.base import Rule, Scope, bundle_from, violation_from
from loan_rules.registry import register
from loan_rules._dates import parse_date

REQUIRED = ("loan_id", "borrower_id", "original_principal", "origination_date")
# Row-local rules apply to BOTH profiles; identity/time rules keep the loan_tape
# default (parent spec §7). `required_fields` and `stale_record` stay loan_tape-only.
BOTH = frozenset({"loan_tape", "sf_performance_panel"})


# --- required_fields -------------------------------------------------------
def _required_check(loan, params):
    for f in params["required"]:
        if loan.get(f) in (None, ""):
            return violation_from(loan, "required_fields", f, loan.get(f), "non-empty",
                                  f"Required field {f} is missing", severity="high")
    return None


def _required_corrupt(loan, rng, params):
    loan = dict(loan)
    f = params["required"][int(rng.integers(len(params["required"])))]
    original = loan.get(f)
    loan[f] = ""
    return loan, bundle_from(loan, "required_fields", f, "", "non-empty",
                             f"Required field {f} is missing", original=original)


register(Rule("required_fields", Scope.ROW, "high",
              MappingProxyType({"required": list(REQUIRED)}),
              "Required field {field} is missing", _required_check, _required_corrupt))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/loan_rules/test_rules_row.py -v`
Expected: PASS (round-trip for `required_fields` + edge)

- [ ] **Step 5: Commit**

```bash
git add loan_rules/_dates.py loan_rules/rules_row.py tests/loan_rules/helpers.py tests/loan_rules/test_rules_row.py
git commit -m "feat(loan_rules): ROW round-trip harness + required_fields"
```

---

### Task 4: Amount ROW rules — `non_negative_amounts`, `balance_le_principal`, `interest_rate_range`

**Files:** Modify `loan_rules/rules_row.py`; Test `tests/loan_rules/test_rules_row.py`.

**Interfaces:** the parametrized `test_row_round_trip` auto-covers each newly-registered rule. Produces `non_negative_amounts` (`{"fields": [...]}`), `balance_le_principal` (`{}`), `interest_rate_range` (`{"min":2.0,"max":36.0}`).

- [ ] **Step 1: Write the failing test**

```python
# add to tests/loan_rules/test_rules_row.py
from decimal import Decimal


def test_non_negative_amounts_edge():
    r = _rule("non_negative_amounts")
    assert r.check(make_clean_loan(current_balance=Decimal("-1.00")), r.params) is not None


def test_balance_le_principal_edge():
    r = _rule("balance_le_principal")
    assert r.check(make_clean_loan(current_balance=Decimal("300000.00"),
                                   original_principal=Decimal("250000.00")), r.params) is not None


def test_interest_rate_range_edge():
    r = _rule("interest_rate_range")
    assert r.check(make_clean_loan(interest_rate=Decimal("45.0")), r.params) is not None
    assert r.check(make_clean_loan(interest_rate=Decimal("5.0")), r.params) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/loan_rules/test_rules_row.py -v`
Expected: FAIL — `StopIteration` in `_rule(...)`

- [ ] **Step 3: Write minimal implementation**

```python
# append to loan_rules/rules_row.py
from decimal import Decimal


def _nonneg_check(loan, params):
    for f in params["fields"]:
        val = loan.get(f)
        if isinstance(val, Decimal) and val < 0:
            return violation_from(loan, "non_negative_amounts", f, val, ">= 0",
                                  f"{f} is negative ({val})", severity="high")
    return None


def _nonneg_corrupt(loan, rng, params):
    loan = dict(loan)
    f = params["fields"][int(rng.integers(len(params["fields"])))]
    original = loan[f]
    loan[f] = -abs(original)
    return loan, bundle_from(loan, "non_negative_amounts", f, loan[f], ">= 0",
                             f"{f} is negative", original=original)


register(Rule("non_negative_amounts", Scope.ROW, "high",
              MappingProxyType({"fields": ["original_principal", "current_balance"]}),
              "{field} is negative", _nonneg_check, _nonneg_corrupt, profiles=BOTH))


def _ble_check(loan, params):
    bal, prin = loan.get("current_balance"), loan.get("original_principal")
    if isinstance(bal, Decimal) and isinstance(prin, Decimal) and bal > prin:
        return violation_from(loan, "balance_le_principal", "current_balance", bal,
                              f"<= {prin}", "current_balance exceeds original_principal",
                              severity="high")
    return None


def _ble_corrupt(loan, rng, params):
    loan = dict(loan)
    original = loan["current_balance"]
    loan["current_balance"] = loan["original_principal"] + Decimal("1000.00")
    return loan, bundle_from(loan, "balance_le_principal", "current_balance",
                             loan["current_balance"], f"<= {loan['original_principal']}",
                             "current_balance exceeds original_principal", original=original)


register(Rule("balance_le_principal", Scope.ROW, "high", MappingProxyType({}),
              "current_balance exceeds original_principal", _ble_check, _ble_corrupt,
              profiles=BOTH))


def _rate_check(loan, params):
    rate = loan.get("interest_rate")
    lo, hi = Decimal(str(params["min"])), Decimal(str(params["max"]))
    if isinstance(rate, Decimal) and not (lo <= rate <= hi):
        return violation_from(loan, "interest_rate_range", "interest_rate", rate,
                              f"{params['min']}-{params['max']}", "interest_rate out of band")
    return None


def _rate_corrupt(loan, rng, params):
    loan = dict(loan)
    original = loan["interest_rate"]
    loan["interest_rate"] = Decimal(str(params["max"])) + Decimal("10.0")
    return loan, bundle_from(loan, "interest_rate_range", "interest_rate",
                             loan["interest_rate"], f"{params['min']}-{params['max']}",
                             "interest_rate out of band", original=original)


register(Rule("interest_rate_range", Scope.ROW, "medium",
              MappingProxyType({"min": 2.0, "max": 36.0}),
              "interest_rate out of band", _rate_check, _rate_corrupt, profiles=BOTH))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/loan_rules/test_rules_row.py -v`
Expected: PASS (round-trip over 4 ROW rules + edges)

- [ ] **Step 5: Commit**

```bash
git add loan_rules/rules_row.py tests/loan_rules/test_rules_row.py
git commit -m "feat(loan_rules): amount ROW rules"
```

---

### Task 5: Date ROW rules — `valid_dates`, `maturity_after_origination`, `stale_record`

**Files:** Modify `loan_rules/rules_row.py`; Test `tests/loan_rules/test_rules_row.py`.

**Interfaces:** Produces `valid_dates` (`{"fields": [...]}`), `maturity_after_origination` (`{}`), `stale_record` (`{"as_of":"2024-07-01","max_age_days":180}`).

- [ ] **Step 1: Write the failing test**

```python
# add to tests/loan_rules/test_rules_row.py
from datetime import date


def test_valid_dates_edge():
    r = _rule("valid_dates")
    assert r.check(make_clean_loan(maturity_date="13/40/2020"), r.params) is not None


def test_maturity_after_origination_edge():
    r = _rule("maturity_after_origination")
    assert r.check(make_clean_loan(origination_date=date(2050, 1, 1),
                                   maturity_date=date(2020, 1, 1)), r.params) is not None


def test_stale_record_edge():
    r = _rule("stale_record")
    assert r.check(make_clean_loan(last_updated_at=date(2000, 1, 1)), r.params) is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/loan_rules/test_rules_row.py -v`
Expected: FAIL — `StopIteration`

- [ ] **Step 3: Write minimal implementation**

```python
# append to loan_rules/rules_row.py
from datetime import timedelta


def _valid_dates_check(loan, params):
    for f in params["fields"]:
        val = loan.get(f)
        if val in (None, ""):
            continue
        if parse_date(val) is None:
            return violation_from(loan, "valid_dates", f, val, "parseable date",
                                  f"{f} is not a valid date", severity="high")
    return None


def _valid_dates_corrupt(loan, rng, params):
    loan = dict(loan)
    f = params["fields"][int(rng.integers(len(params["fields"])))]
    original = loan[f]
    loan[f] = "13/40/2020"
    return loan, bundle_from(loan, "valid_dates", f, loan[f], "parseable date",
                             f"{f} is not a valid date", original=original)


register(Rule("valid_dates", Scope.ROW, "high",
              MappingProxyType({"fields": ["origination_date", "maturity_date",
                                           "last_payment_date", "last_updated_at"]}),
              "{field} is not a valid date", _valid_dates_check, _valid_dates_corrupt,
              profiles=BOTH))


def _mao_check(loan, params):
    o, m = parse_date(loan.get("origination_date")), parse_date(loan.get("maturity_date"))
    if o and m and m < o:
        return violation_from(loan, "maturity_after_origination", "maturity_date", m,
                              f">= {o}", "maturity_date precedes origination_date", severity="high")
    return None


def _mao_corrupt(loan, rng, params):
    loan = dict(loan)
    o = parse_date(loan["origination_date"])
    original = loan["maturity_date"]
    loan["maturity_date"] = o - timedelta(days=365)
    return loan, bundle_from(loan, "maturity_after_origination", "maturity_date",
                             loan["maturity_date"], f">= {o}",
                             "maturity_date precedes origination_date", original=original)


register(Rule("maturity_after_origination", Scope.ROW, "high", MappingProxyType({}),
              "maturity_date precedes origination_date", _mao_check, _mao_corrupt,
              profiles=BOTH))


def _stale_check(loan, params):
    as_of, lu = parse_date(params["as_of"]), parse_date(loan.get("last_updated_at"))
    if lu and (as_of - lu).days > params["max_age_days"]:
        return violation_from(loan, "stale_record", "last_updated_at", lu,
                              f"within {params['max_age_days']}d of {as_of}",
                              "record is stale", severity="low")
    return None


def _stale_corrupt(loan, rng, params):
    loan = dict(loan)
    as_of = parse_date(params["as_of"])
    original = loan["last_updated_at"]
    loan["last_updated_at"] = as_of - timedelta(days=params["max_age_days"] + 400)
    return loan, bundle_from(loan, "stale_record", "last_updated_at",
                             loan["last_updated_at"], f"within {params['max_age_days']}d",
                             "record is stale", original=original)


register(Rule("stale_record", Scope.ROW, "low",
              MappingProxyType({"as_of": "2024-07-01", "max_age_days": 180}),
              "record is stale", _stale_check, _stale_corrupt))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/loan_rules/test_rules_row.py -v`
Expected: PASS (7 ROW rules + edges)

- [ ] **Step 5: Commit**

```bash
git add loan_rules/rules_row.py tests/loan_rules/test_rules_row.py
git commit -m "feat(loan_rules): date ROW rules"
```

---

### Task 6: Categorical ROW rules — `valid_state_code`, `payment_status_vs_dpd`, `closed_with_balance`

**Files:** Modify `loan_rules/rules_row.py`; Test `tests/loan_rules/test_rules_row.py`.

**Interfaces:** Produces `valid_state_code` (`{"states":[...51...]}`), `payment_status_vs_dpd` (`{}`), `closed_with_balance` (`{}`). Completes the 10 ROW rules.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/loan_rules/test_rules_row.py
def test_valid_state_code_edge():
    r = _rule("valid_state_code")
    assert r.check(make_clean_loan(borrower_state="ZZ"), r.params) is not None


def test_payment_status_vs_dpd_edge():
    r = _rule("payment_status_vs_dpd")
    assert r.check(make_clean_loan(payment_status="CURRENT", days_past_due=90), r.params) is not None


def test_closed_with_balance_edge():
    r = _rule("closed_with_balance")
    assert r.check(make_clean_loan(payment_status="CLOSED",
                                   current_balance=Decimal("5000.00")), r.params) is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/loan_rules/test_rules_row.py -v`
Expected: FAIL — `StopIteration`

- [ ] **Step 3: Write minimal implementation**

```python
# append to loan_rules/rules_row.py
US_STATES = [
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
    "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
    "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
    "VA","WA","WV","WI","WY","DC",
]


def _state_check(loan, params):
    st = loan.get("borrower_state")
    if st not in params["states"]:
        return violation_from(loan, "valid_state_code", "borrower_state", st,
                              "valid US code", "borrower_state is not a valid US code")
    return None


def _state_corrupt(loan, rng, params):
    loan = dict(loan)
    original = loan["borrower_state"]
    loan["borrower_state"] = "ZZ"
    return loan, bundle_from(loan, "valid_state_code", "borrower_state", "ZZ",
                             "valid US code", "borrower_state is not a valid US code",
                             original=original)


register(Rule("valid_state_code", Scope.ROW, "medium",
              MappingProxyType({"states": US_STATES}),
              "borrower_state is not a valid US code", _state_check, _state_corrupt,
              profiles=BOTH))


def _psd_check(loan, params):
    status, dpd = loan.get("payment_status"), loan.get("days_past_due")
    if not isinstance(dpd, int):
        return None
    if status == "CURRENT" and dpd > 0:
        return violation_from(loan, "payment_status_vs_dpd", "days_past_due", dpd,
                              "0 for CURRENT", "CURRENT loan has positive days_past_due")
    if status == "DELINQUENT" and dpd == 0:
        return violation_from(loan, "payment_status_vs_dpd", "days_past_due", dpd,
                              ">0 for DELINQUENT", "DELINQUENT loan has days_past_due=0")
    return None


def _psd_corrupt(loan, rng, params):
    loan = dict(loan)
    original = loan["days_past_due"]
    loan["payment_status"] = "CURRENT"
    loan["days_past_due"] = 90
    return loan, bundle_from(loan, "payment_status_vs_dpd", "days_past_due", 90,
                             "0 for CURRENT", "CURRENT loan has positive days_past_due",
                             original=original)


register(Rule("payment_status_vs_dpd", Scope.ROW, "medium", MappingProxyType({}),
              "payment_status inconsistent with days_past_due", _psd_check, _psd_corrupt,
              profiles=BOTH))


def _cwb_check(loan, params):
    bal = loan.get("current_balance")
    if loan.get("payment_status") == "CLOSED" and isinstance(bal, Decimal) and bal > 0:
        return violation_from(loan, "closed_with_balance", "current_balance", bal,
                              "0 for CLOSED", "CLOSED loan has positive balance", severity="high")
    return None


def _cwb_corrupt(loan, rng, params):
    loan = dict(loan)
    original = loan["current_balance"]
    loan["payment_status"] = "CLOSED"
    loan["current_balance"] = Decimal("5000.00")
    return loan, bundle_from(loan, "closed_with_balance", "current_balance",
                             Decimal("5000.00"), "0 for CLOSED",
                             "CLOSED loan has positive balance", original=original)


register(Rule("closed_with_balance", Scope.ROW, "high", MappingProxyType({}),
              "CLOSED loan has positive balance", _cwb_check, _cwb_corrupt, profiles=BOTH))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/loan_rules/test_rules_row.py -v`
Expected: PASS (10 ROW rules + edges)

- [ ] **Step 5: Commit**

```bash
git add loan_rules/rules_row.py tests/loan_rules/test_rules_row.py
git commit -m "feat(loan_rules): categorical ROW rules (10 ROW rules complete)"
```

---

### Task 7: DATASET context + runner + round-trip harness + `duplicate_loan_id`

**Files:**
- Create: `loan_rules/context.py`, `loan_rules/rules_dataset.py`
- Modify: `tests/loan_rules/helpers.py`, `loan_rules/__init__.py`
- Test: `tests/loan_rules/test_rules_dataset.py`, `tests/loan_rules/test_runner.py`

**Interfaces:**
- Produces: `build_context(ds) -> dict` (`loan_id_counts`, `combo_counts`, `borrower_counts`, `servicer_by_loan`, `manifest_ids`); `validate_dataset(ds, rules) -> list[Violation]` (dispatch ROW per-loan / DATASET whole-dataset; sets `v.severity = rule.severity`); DATASET contract `check(ds, ctx, params) -> list[Violation]`, `corrupt(ds, rng, params, avoid=None) -> (ds, list[Bundle])` (the optional `avoid` set of `row_uid`s defaults to `None` so the per-rule round-trip tests call it unchanged); selection helpers `_eligible_indices`/`_pick_two`/`_pick_one`; `make_clean_dataset(n=6) -> Dataset` (row_uids + exact servicer echoes + full manifest); first DATASET rule `duplicate_loan_id` (keys both members on their **own** `row_uid`, picks victim+source outside `avoid`).

- [ ] **Step 1: Write the failing test**

```python
# add to tests/loan_rules/helpers.py
from loan_rules.base import Dataset


def make_clean_dataset(n=6):
    loans = [make_clean_loan(i) for i in range(n)]
    servicer = [{"loan_id": l["loan_id"], "current_balance": l["current_balance"],
                 "interest_rate": l["interest_rate"], "payment_status": l["payment_status"]}
                for l in loans[: max(1, n // 2)]]
    manifest = [{"loan_id": l["loan_id"], "document_status": "COMPLETE"} for l in loans]
    return Dataset(loans=loans, servicer_updates=servicer, manifest=manifest)
```

```python
# tests/loan_rules/test_rules_dataset.py
import numpy as np
import pytest
from loan_rules.base import Scope
from loan_rules import registry
from loan_rules.context import build_context
import loan_rules.rules_dataset  # noqa: F401
from tests.loan_rules.helpers import make_clean_dataset

DATASET_RULES = [r for r in registry.ALL_RULES if r.scope == Scope.DATASET]


def _rule(rid):
    return next(r for r in DATASET_RULES if r.id == rid)


@pytest.mark.parametrize("rule", DATASET_RULES, ids=lambda r: r.id)
def test_dataset_round_trip(rule):
    rng = np.random.default_rng(0)
    clean = make_clean_dataset()
    assert rule.check(clean, build_context(clean), rule.params) == [], "clean must pass"
    ds2, bundles = rule.corrupt(make_clean_dataset(), rng, rule.params)
    flagged = {v.row_uid for v in rule.check(ds2, build_context(ds2), rule.params)}
    implicated = {b.row_uid for b in bundles}
    assert implicated and implicated <= flagged, f"{rule.id}: implicated not all flagged"


def test_duplicate_loan_id_flags_two_distinct_rows():
    rng = np.random.default_rng(1)
    _, bundles = _rule("duplicate_loan_id").corrupt(make_clean_dataset(), rng, {})
    assert len({b.row_uid for b in bundles}) == 2   # keyed on row_uid, not loan_id
```

```python
# tests/loan_rules/test_runner.py
from loan_rules import load_rules, validate_dataset
from tests.loan_rules.helpers import make_clean_dataset


def test_clean_dataset_has_no_violations():
    assert validate_dataset(make_clean_dataset(), load_rules(None)) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/loan_rules/test_rules_dataset.py tests/loan_rules/test_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'loan_rules.context'`

- [ ] **Step 3: Write minimal implementation**

```python
# loan_rules/context.py
from __future__ import annotations
from collections import Counter
from loan_rules.base import Dataset, Scope, Violation


def build_context(ds: Dataset) -> dict:
    return {
        "loan_id_counts": Counter(l.get("loan_id") for l in ds.loans),
        "combo_counts": Counter(
            (l.get("borrower_id"), str(l.get("original_principal")), str(l.get("origination_date")))
            for l in ds.loans),
        "borrower_counts": Counter(l.get("borrower_id") for l in ds.loans),
        "servicer_by_loan": {s["loan_id"]: s for s in ds.servicer_updates},
        "manifest_ids": {m["loan_id"] for m in ds.manifest},
    }


def validate_dataset(ds: Dataset, rules) -> list[Violation]:
    ctx = build_context(ds)
    out: list[Violation] = []
    for rule in rules:
        if rule.scope == Scope.ROW:
            for loan in ds.loans:
                v = rule.check(loan, rule.params)
                if v is not None:
                    v.severity = rule.severity
                    out.append(v)
        else:
            for v in rule.check(ds, ctx, rule.params):
                v.severity = rule.severity
                out.append(v)
    return out
```

```python
# loan_rules/rules_dataset.py
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
```

Add to `loan_rules/__init__.py`:

```python
from loan_rules.context import build_context, validate_dataset
__all__ += ["build_context", "validate_dataset"]
```

Because bundles are keyed on `row_uid`, the two collision members are distinct oracle entries even though they share a `loan_id` — this is what makes `test_duplicate_loan_id_flags_two_distinct_rows` pass and removes the mutable-key orphaning.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/loan_rules/ -v`
Expected: PASS (dataset round-trip for `duplicate_loan_id`; runner clean; ROW rules still green)

- [ ] **Step 5: Commit**

```bash
git add loan_rules/context.py loan_rules/rules_dataset.py loan_rules/__init__.py tests/loan_rules/
git commit -m "feat(loan_rules): dataset context + runner + duplicate_loan_id (row_uid-keyed)"
```

---

### Task 8: Row-multiplying DATASET rules — `duplicate_borrower_combo`, `suspicious_borrower_repeat`

**Files:** Modify `loan_rules/rules_dataset.py`; Test `tests/loan_rules/test_rules_dataset.py`.

**Interfaces:** Produces `duplicate_borrower_combo` (repurposes a row so the `(borrower_id, original_principal, origination_date)` combo collides — two distinct `row_uid`s flagged, no rows added) and `suspicious_borrower_repeat` (`{"max_repeats":3}`; **synthesizes a fresh borrower** and appends `max_repeats+2` new rows for it — every new row is a fresh, always-distinct `row_uid`; no dependence on existing data, so repeated calls never inflate ambiguously).

- [ ] **Step 1: Write the failing test**

```python
# add to tests/loan_rules/test_rules_dataset.py
def test_suspicious_borrower_repeat_adds_fixed_cluster():
    r = _rule("suspicious_borrower_repeat")
    ds = make_clean_dataset(n=6)
    before = len(ds.loans)
    ds2, bundles = r.corrupt(ds, np.random.default_rng(2), r.params)
    assert len(ds2.loans) == before + (r.params["max_repeats"] + 2)
    assert len({b.row_uid for b in bundles}) == r.params["max_repeats"] + 2


def test_duplicate_borrower_combo_repurposes_row():
    r = _rule("duplicate_borrower_combo")
    ds = make_clean_dataset(n=6)
    before = len(ds.loans)
    ds2, bundles = r.corrupt(ds, np.random.default_rng(3), r.params)
    assert len(ds2.loans) == before                       # no rows added
    assert len({b.row_uid for b in bundles}) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/loan_rules/test_rules_dataset.py -v`
Expected: FAIL — `StopIteration`

- [ ] **Step 3: Write minimal implementation**

```python
# append to loan_rules/rules_dataset.py
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
```

Note: `_repeat_corrupt` invents a brand-new `borrower_id` and fixed-size cluster, so it never depends on (or collides with) existing rows and adds exactly `max_repeats+2` rows per call — this is what removes the row-inflation ambiguity of the earlier design and keeps `loan_rules` free of any `tests` import.

Note (null-safety): both borrower-keyed checks skip loans whose `borrower_id is None`. On the synthetic tape every loan has a `borrower_id`, so this is a no-op for the generator/oracle; it matters for real sources (e.g. the FNMA connector) where `borrower_id` is uniformly null — without it, `{None: N}` would flag *every* loan as a suspicious repeat. A null borrower is "unknown", not "repeated", so this is also the correct behavior on any real loan tape.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/loan_rules/test_rules_dataset.py -v`
Expected: PASS (3 dataset rules round-trip + mechanics)

- [ ] **Step 5: Commit**

```bash
git add loan_rules/rules_dataset.py tests/loan_rules/test_rules_dataset.py
git commit -m "feat(loan_rules): duplicate_borrower_combo + suspicious_borrower_repeat"
```

---

### Task 9: Cross-file DATASET rules — `source_conflict`, `document_status_present`

**Files:** Modify `loan_rules/rules_dataset.py`; Test `tests/loan_rules/test_rules_dataset.py`.

**Interfaces:** Produces `source_conflict` (`{"fields":["current_balance","interest_rate","payment_status"]}`; `corrupt` picks a loan **by index**, get-or-creates its servicer row, sets a conflicting value — no lookup by mutable `loan_id`) and `document_status_present` (`{}`; flags loans whose `loan_id ∉ manifest_ids`). Completes all 15 rules.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/loan_rules/test_rules_dataset.py
def test_source_conflict_sets_sibling_value():
    r = _rule("source_conflict")
    _, bundles = r.corrupt(make_clean_dataset(), np.random.default_rng(4), r.params)
    assert bundles and all(b.sibling_value is not None for b in bundles)


def test_document_status_present_edge():
    r = _rule("document_status_present")
    ds = make_clean_dataset()
    ds.manifest.pop()
    flagged = {v.row_uid for v in r.check(ds, build_context(ds), r.params)}
    assert flagged
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/loan_rules/test_rules_dataset.py -v`
Expected: FAIL — `StopIteration`

- [ ] **Step 3: Write minimal implementation**

```python
# append to loan_rules/rules_dataset.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/loan_rules/ -v`
Expected: PASS (all 15 rules round-trip + edges)

- [ ] **Step 5: Commit**

```bash
git add loan_rules/rules_dataset.py tests/loan_rules/test_rules_dataset.py
git commit -m "feat(loan_rules): source_conflict + document_status_present (15 rules complete)"
```

---

### Task 10: Correlated clean builders (assign `row_uid`)

**Files:**
- Create: `data/__init__.py` (empty), `data/_clean.py`
- Test: `tests/data/test_clean.py`

**Interfaces:**
- Produces: `build_clean_loan(rng, i) -> Loan` (all §4 invariants; carries `row_uid=f"U{i:05d}"`); `build_clean_dataset(n, seed) -> Dataset` (n loans, ~40% servicer echoes with exact values, full manifest; seeds numpy **and** Faker).

- [ ] **Step 1: Write the failing test**

```python
# tests/data/test_clean.py
from loan_rules import load_rules, validate_dataset
from data._clean import build_clean_dataset


def test_clean_dataset_passes_every_rule():
    ds = build_clean_dataset(n=300, seed=7)
    v = validate_dataset(ds, load_rules(None))
    assert v == [], f"clean tripped: {[x.rule_id for x in v][:5]}"


def test_clean_dataset_reproducible():
    a, b = build_clean_dataset(50, 1), build_clean_dataset(50, 1)
    assert [l["interest_rate"] for l in a.loans] == [l["interest_rate"] for l in b.loans]
    assert [l["row_uid"] for l in a.loans] == [l["row_uid"] for l in b.loans]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/data/test_clean.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'data._clean'`

- [ ] **Step 3: Write minimal implementation**

```python
# data/_clean.py
from __future__ import annotations
from datetime import date, timedelta
from decimal import Decimal
import numpy as np
from faker import Faker
from loan_rules.base import Dataset

CREDIT_GRADES = ["A", "B", "C", "D"]
RATE_BAND = {"A": (4.0, 6.0), "B": (6.0, 8.0), "C": (8.0, 11.0), "D": (11.0, 15.0)}
LOAN_TYPES = ["FIXED", "ARM"]
PURPOSES = ["PURCHASE", "REFI", "CASHOUT"]
INCOME_BANDS = ["<50K", "50K-100K", "100K-150K", ">150K"]
STATUSES = ["CURRENT", "DELINQUENT", "CLOSED"]
STATES = ["CA", "TX", "NY", "FL", "WA", "IL", "PA", "OH", "GA", "NC"]
SERVICERS = ["Acme Servicing", "BlueRiver Loan Servicing", "Cardinal Mortgage Co"]
AS_OF = date(2024, 7, 1)


def _money(rng, lo, hi):
    return Decimal(str(round(float(rng.uniform(lo, hi)), 2))).quantize(Decimal("0.01"))


def _pick(rng, seq):
    return seq[int(rng.integers(len(seq)))]


def build_clean_loan(rng, i):
    grade = _pick(rng, CREDIT_GRADES)
    lo, hi = RATE_BAND[grade]
    principal = _money(rng, 50_000, 500_000)
    status = _pick(rng, STATUSES)
    orig = date(2015, 1, 1) + timedelta(days=int(rng.integers(0, 2500)))
    term = int(rng.choice([120, 180, 240, 360]))
    if status == "CLOSED":
        balance, dpd = Decimal("0.00"), 0
    else:
        balance = (principal * Decimal(str(round(float(rng.uniform(0.3, 0.95)), 2)))).quantize(Decimal("0.01"))
        dpd = 0 if status == "CURRENT" else int(rng.integers(30, 180))
    return {
        "row_uid": f"U{i:05d}", "loan_id": f"LN{i:05d}", "borrower_id": f"BR{i:05d}",
        "loan_type": _pick(rng, LOAN_TYPES), "origination_date": orig,
        "maturity_date": orig + timedelta(days=term * 30),
        "original_principal": principal, "current_balance": balance,
        "interest_rate": _money(rng, lo, hi), "term_months": term,
        "borrower_state": _pick(rng, STATES), "loan_purpose": _pick(rng, PURPOSES),
        "credit_grade": grade, "employment_length": int(rng.integers(0, 35)),
        "income_band": _pick(rng, INCOME_BANDS), "payment_status": status,
        "days_past_due": dpd, "servicer_name": _pick(rng, SERVICERS),
        "last_payment_date": AS_OF - timedelta(days=int(rng.integers(1, 60))),
        "last_updated_at": AS_OF - timedelta(days=int(rng.integers(1, 120))),
        "document_status": "COMPLETE", "source_system": "ORIG_SYS",
    }


def build_clean_dataset(n, seed):
    rng = np.random.default_rng(seed)
    Faker().seed_instance(seed)                 # seed Faker even if unused, for future name fields
    loans = [build_clean_loan(rng, i) for i in range(n)]
    servicer = [{"loan_id": l["loan_id"], "current_balance": l["current_balance"],
                 "interest_rate": l["interest_rate"], "payment_status": l["payment_status"]}
                for l in loans if rng.random() < 0.40]
    manifest = [{"loan_id": l["loan_id"], "document_status": l["document_status"]} for l in loans]
    return Dataset(loans=loans, servicer_updates=servicer, manifest=manifest)
```

Note: `maturity = orig + term*30 days` satisfies `maturity_after_origination` (only `>=` matters); `stale_record.as_of` default matches `AS_OF`, so clean `last_updated_at` (≤120d back) passes; servicer echoes exact values so `source_conflict` stays clean.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/data/test_clean.py -v`
Expected: PASS (clean data trips zero rules; reproducible)

- [ ] **Step 5: Commit**

```bash
git add data/__init__.py data/_clean.py tests/data/test_clean.py
git commit -m "feat(data): correlated clean builders with row_uid"
```

---

### Task 11: ROW defect allocation (honors `defect_rate`)

**Files:**
- Create: `data/_allocate.py`
- Test: `tests/data/test_allocate.py`

**Interfaces:**
- Produces: `plan_row_defects(row_rule_ids, eligible_indices, rng, n_loans, per_type=35, defect_rate=0.10, max_per_row=2) -> dict[int, list[str]]` mapping loan index → ROW rule-ids (≤`max_per_row`, spread round-robin across `~defect_rate × n_loans` distinct rows, growing only if per-type targets can't fit under the cap; only draws from `eligible_indices`).

- [ ] **Step 1: Write the failing test**

```python
# tests/data/test_allocate.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/data/test_allocate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'data._allocate'`

- [ ] **Step 3: Write minimal implementation**

```python
# data/_allocate.py
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
```

Note: `slots = chosen * max_per_row` orders as `[r0,r1,…,rN, r0,r1,…,rN]`, so the first `len(chosen)` assignments each land on a distinct row before any row gets a second — this is the round-robin spread that makes `defect_rate` meaningful (fixing the earlier `[r0,r0,r1,r1,…]` bug that packed ~175 rows). Two identical rule-ids can still co-locate rarely; the generator dedupes per row in Task 13.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/data/test_allocate.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add data/_allocate.py tests/data/test_allocate.py
git commit -m "feat(data): ROW defect allocation honoring defect_rate"
```

---

### Task 12: Stable serializers + users.json

**Files:**
- Create: `data/_serialize.py`
- Test: `tests/data/test_serialize.py`

**Interfaces:**
- Produces: `CANONICAL_COLUMNS` (21 fields, order); `format_value(v) -> str`; `write_loans_csv(path, loans)`; `write_rows_csv(path, rows, columns)`; `write_ground_truth_csv(path, bundles)` (columns include `row_uid` + `original_value`); `write_sample_csv(path, bundles)` (**human-facing columns only — no `row_uid`, no `original_value`**); `write_users_json(path, users)` (bcrypt).

- [ ] **Step 1: Write the failing test**

```python
# tests/data/test_serialize.py
from datetime import date
from decimal import Decimal
from loan_rules.base import Bundle
from data._serialize import (format_value, write_loans_csv, write_sample_csv,
                             CANONICAL_COLUMNS)
from tests.loan_rules.helpers import make_clean_loan


def test_format_value_stable():
    assert format_value(Decimal("5")) == "5.00"
    assert format_value(date(2020, 1, 2)) == "2020-01-02"
    assert format_value(None) == ""


def test_loans_csv_header_is_canonical_only(tmp_path):
    p = tmp_path / "loan_tape.csv"
    write_loans_csv(str(p), [make_clean_loan()])
    header = p.read_text().splitlines()[0]
    assert header == ",".join(CANONICAL_COLUMNS)      # no row_uid leaked into the tape


def test_loans_csv_byte_identical(tmp_path):
    loans = [make_clean_loan(i) for i in range(20)]
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    write_loans_csv(str(a), loans); write_loans_csv(str(b), loans)
    assert a.read_bytes() == b.read_bytes()


def test_sample_excludes_oracle_columns(tmp_path):
    p = tmp_path / "sample.csv"
    write_sample_csv(str(p), [Bundle("U1", "LN1", "r", "f", 1, 2, "m", original_value=0)])
    header = p.read_text().splitlines()[0]
    assert "row_uid" not in header and "original_value" not in header
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/data/test_serialize.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'data._serialize'`

- [ ] **Step 3: Write minimal implementation**

```python
# data/_serialize.py
from __future__ import annotations
import csv
import json
from datetime import date
from decimal import Decimal
import bcrypt

CANONICAL_COLUMNS = [
    "loan_id", "borrower_id", "loan_type", "origination_date", "maturity_date",
    "original_principal", "current_balance", "interest_rate", "term_months",
    "borrower_state", "loan_purpose", "credit_grade", "employment_length",
    "income_band", "payment_status", "days_past_due", "servicer_name",
    "last_payment_date", "last_updated_at", "document_status", "source_system",
]
_GT_COLUMNS = ["row_uid", "loan_id", "rule_id", "field", "observed_value", "expected",
               "sibling_value", "original_value", "message"]
_SAMPLE_COLUMNS = ["loan_id", "rule_id", "field", "observed_value", "expected",
                   "sibling_value", "message"]


def format_value(v):
    if v is None:
        return ""
    if isinstance(v, Decimal):
        return str(v.quantize(Decimal("0.01")))
    if isinstance(v, date):
        return v.isoformat()
    return str(v)


def _write(path, columns, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(columns)
        for r in rows:
            w.writerow([format_value(r.get(c) if isinstance(r, dict) else getattr(r, c, None))
                        for c in columns])


def write_loans_csv(path, loans):
    _write(path, CANONICAL_COLUMNS, loans)


def write_rows_csv(path, rows, columns):
    _write(path, columns, rows)


def write_ground_truth_csv(path, bundles):
    _write(path, _GT_COLUMNS, bundles)


def write_sample_csv(path, bundles):
    _write(path, _SAMPLE_COLUMNS, bundles)


def write_users_json(path, users):
    out = [{"username": u["username"], "role": u["role"], "display_name": u["display_name"],
            "password_hash": bcrypt.hashpw(u["password"].encode(), bcrypt.gensalt()).decode()}
           for u in users]
    with open(path, "w") as f:
        json.dump(out, f, sort_keys=True, indent=2)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/data/test_serialize.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add data/_serialize.py tests/data/test_serialize.py
git commit -m "feat(data): deterministic serializers (tape excludes row_uid; sample excludes oracle cols)"
```

---

### Task 13: The generator — `build_package` (in-memory oracle) + `generate` (files)

**Files:**
- Create: `data/generate.py`
- Test: `tests/data/test_generate.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `build_package(rules, rows, defect_rate, seed) -> (Dataset, list[Bundle])` — pure, in-memory: builds clean data, applies DATASET corruptions first (safe order, distinct-loan targets), excludes their loans from the ROW pool, applies ROW corruptions, repairs the manifest for **added cluster rows only**. `generate(out_dir, rows=5000, defect_rate=0.10, seed=1234) -> dict` — writes default rules json, loads rules, calls `build_package`, writes the 7 files, returns summary. `main()` CLI.

- [ ] **Step 1: Write the failing test**

```python
# tests/data/test_generate.py
import csv
import hashlib
from collections import Counter
import pytest
from loan_rules import load_rules, validate_dataset, write_default_rules_json
from data.generate import build_package, generate

REPRO = ["loan_tape.csv", "servicer_update.csv", "document_manifest.csv",
         "validation_rules.json", "expected_exception_sample.csv", "ground_truth_exceptions.csv"]


def _hash(d):
    h = hashlib.sha256()
    for name in REPRO:
        h.update((d / name).read_bytes())
    return h.hexdigest()


def test_reproducible_excluding_users_json(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    generate(str(a), rows=800, seed=42); generate(str(b), rows=800, seed=42)
    assert _hash(a) == _hash(b)


@pytest.mark.parametrize("seed", [1, 7, 42, 100, 2024])   # composition must hold on every seed
def test_superset_oracle_in_memory(tmp_path, seed):
    rules_path = tmp_path / "validation_rules.json"
    write_default_rules_json(str(rules_path))
    rules = load_rules(str(rules_path))
    ds, bundles = build_package(rules, rows=800, defect_rate=0.10, seed=seed)
    ground_pairs = {(b.row_uid, b.rule_id) for b in bundles}
    found = validate_dataset(ds, rules)
    found_pairs = {(v.row_uid, v.rule_id) for v in found}
    assert ground_pairs <= found_pairs, f"missing: {ground_pairs - found_pairs}"
    ground_uids = {b.row_uid for b in bundles}
    assert {v.row_uid for v in found} <= ground_uids, "a clean loan was flagged"


def test_every_type_meets_target(tmp_path):
    out = tmp_path / "o"; out.mkdir()
    generate(str(out), rows=5000, seed=42)
    c = Counter()
    with open(out / "ground_truth_exceptions.csv") as f:
        for row in csv.DictReader(f):
            c[row["rule_id"]] += 1
    for r in load_rules(None):
        assert c[r.id] >= 30, f"{r.id}={c[r.id]}"


def test_defective_share_reasonable(tmp_path):
    out = tmp_path / "o"; out.mkdir()
    summary = generate(str(out), rows=5000, seed=42)
    uids = set()
    with open(out / "ground_truth_exceptions.csv") as f:
        for row in csv.DictReader(f):
            uids.add(row["row_uid"])
    share = len(uids) / summary["rows"]
    assert 0.08 <= share <= 0.20, share      # ROW ~7% + DATASET-implicated ~ up to ~13%
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/data/test_generate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'data.generate'`

- [ ] **Step 3: Write minimal implementation**

```python
# data/generate.py
from __future__ import annotations
import argparse
import os
import numpy as np
from loan_rules import load_rules, write_default_rules_json
from loan_rules.base import Scope
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
                              per_type=35, defect_rate=defect_rate)
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
```

**Executor note:** the in-memory `build_package` is the oracle surface — no CSV reload/coercion round-trip is needed to prove injection⇒detection, which removes a whole class of type-coercion bugs. `test_reproducible_excluding_users_json` separately covers the file-writing path. If `test_superset_oracle_in_memory` ever reports "a clean loan was flagged", it means a corruption implicated a loan without emitting its bundle — fix the offending `corrupt`, do not weaken the assertion.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/data/test_generate.py -v`
Expected: PASS (reproducible sans users.json; superset oracle holds; targets met; share 8–20%)

- [ ] **Step 5: Commit**

```bash
git add data/generate.py tests/data/test_generate.py
git commit -m "feat(data): generator (row_uid oracle, dataset-first, manifest-safe, defect_rate)"
```

---

### Task 14: Makefile + import-purity guard + full suite

**Files:**
- Create: `Makefile`, `tests/loan_rules/test_import_purity.py`

**Interfaces:** `make seed` / `make test` / `make install`; a test proving `loan_rules` imports no Mongo/app/`tests`/pandas modules.

- [ ] **Step 1: Write the failing test**

```python
# tests/loan_rules/test_import_purity.py
import subprocess
import sys


def test_loan_rules_is_import_pure():
    code = (
        "import sys, loan_rules, loan_rules.rules_row, loan_rules.rules_dataset,"
        " loan_rules.context, loan_rules.registry;"
        "bad=[m for m in set(sys.modules) if m.split('.')[0] in "
        "{'motor','beanie','pymongo','fastapi','tests','pandas'}];"
        "assert not bad, bad; print('ok')"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "ok" in r.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/loan_rules/test_import_purity.py -v`
Expected: FAIL — `ModuleNotFoundError` (Makefile/test absent) or, if run before, PASS. If it fails on a `tests`/`pandas` import leaking from `loan_rules`, that is a real purity regression to fix in the offending module.

- [ ] **Step 3: Write minimal implementation**

```makefile
# Makefile
.PHONY: install seed test
install:
	pip install -e ".[dev]"

seed:
	python -m data.generate --rows 5000 --seed 1234 --out-dir data

test:
	pytest -q
```

- [ ] **Step 4: Run full suite + seed**

Run: `pytest -q && make seed`
Expected: entire suite green; `make seed` writes 7 files into `data/` (`loan_tape.csv` has 5,000 + cluster rows, 21 columns, no `row_uid`).

- [ ] **Step 5: Commit**

```bash
git add Makefile tests/loan_rules/test_import_purity.py
git commit -m "feat: make targets + loan_rules import-purity guard"
```

---

## Self-Review

**1. Spec coverage** (data-generator spec §-by-§):
- §2 outputs (7 files) → Tasks 12–13. ✓
- §3 Rule object, explicit params, **hashable-by-id** (`compare=False` on all non-`id` fields, incl. `params`) → Task 1. Standalone import-pure package + editable install → Task 1, guard Task 14. ✓
- §4 correlated clean rows → Task 10. ✓
- §5 one-shot allocation, ≤2 cap + round-robin spread, grow-set, enabled-only, **defective-set ≡ ground-truth `row_uid`s**, DATASET mechanics (repurpose vs fresh cluster), partner bundles → Tasks 8, 9, 11, 13. ✓
- §6 servicer ~40% + conflict sibling; manifest omission (and safe repair) → Tasks 9, 10, 13. ✓
- §7 one-shape bundle + no `corrupted_value`; minimal LLM grounding → Task 1 types, used throughout. ✓
- §8 validation_rules.json single source + disabled-rule skip → Tasks 2, 13 (`by_id.get` skips filtered rules). ✓
- §9 two seeded RNGs (numpy spawn + Faker.seed_instance), stable float/column/sort_keys → Tasks 10, 12, 13. ✓
- §10 ROW + DATASET round-trip, reproducibility (excl. users.json), type coverage, **superset oracle**, cross-file linkage → Tasks 3, 7, 13. ✓
- All 15 rule types → Tasks 3–9. ✓

**2. Prior-review defects — status:**
- Hashability (#1) → fixed in Task 1 (`compare=False` incl. `params`); test asserts `{r,r}` works. ✓
- Dup "both members" (#2) → keyed on `row_uid`; `test_duplicate_loan_id_flags_two_distinct_rows` asserts size 2. ✓
- Manifest reversal (#3) → Task 13 repairs manifest for **added cluster rows only** (`row_uid ∉ initial_uids`), never re-adding doc-removed originals. ✓
- Orphaning (#4) → `row_uid` is immutable; ROW bundles survive `loan_id` mutation; DATASET runs first and ROW excludes implicated loans. ✓
- Conflict lookup crash (#5) → `_conflict_corrupt` picks by index and get-or-creates the servicer row. ✓
- Minor a (sample cols) → `write_sample_csv` excludes `row_uid`/`original_value`. ✓ Minor b (`defect_rate`) → round-robin spread + budget in `plan_row_defects`, test asserts share. ✓ Minor c (dead `STATES and`) → replaced with `_pick`. ✓ Minor d (dataset replacement/inflation) → `_apply_dataset_rule` targets distinct `row_uid`s; `_repeat_corrupt` adds a fixed fresh cluster. ✓

**3rd-review composition defects — status:**
- N1 (repurpose rules dissolve earlier collisions) → the `avoid` set threaded through `_apply_dataset_rule` (each call adds every touched `row_uid` to `local_avoid`) means `_dupid_corrupt`/`_combo_corrupt` never re-pick a prior partner. ✓
- N5 (`duplicate_loan_id` rewrites the join key of earlier cross-file rules) → `avoid` carries the accumulated `dataset_uids`, so `duplicate_loan_id` (and `duplicate_borrower_combo`) never target a loan `source_conflict`/`document_status_present` already joined on. ✓
- Composition coverage → `test_superset_oracle_in_memory` is parametrized over 5 seeds so a single lucky draw can't hide a composition bug. ✓
- Note: `_apply_dataset_rule` now uses the `PER_TYPE_TARGET` constant (was a hardcoded `35`). `Faker().seed_instance` remains seeded-but-currently-unused, honestly labeled dead until name fields exist.

**3. Type/name consistency:** `Bundle`/`Violation`/`Dataset`/`Rule` fields (Task 1) used consistently; ROW `check(loan, params)`/`corrupt(loan, rng, params)` and DATASET `check(ds, ctx, params)`/`corrupt(ds, rng, params)` uniform across Tasks 3–9 and consumed by `validate_dataset` (Task 7); `plan_row_defects` return type (dict[int, list[str]]) matches its use in Task 13; `build_package`/`generate` signatures match tests.

---

## Notes for the executor

- **Why in-memory oracle:** Task 13 validates the `Dataset` object `build_package` returns, not a reloaded CSV — this is both correct (same objects the corruptions produced) and free of coercion bugs. Reproducibility is proven separately over the written files.
- **Do not** add pandas/Mongo to `loan_rules`; ingestion (pandas) is Module A in the parent spec.
- **`per_type=35` vs `>=30` assertion:** allocation targets 35 but the coverage test allows ≥30 to tolerate the rare same-rule co-location that dedupes on a row.
- **If the superset oracle flags a non-ground-truth loan:** find the `corrupt` that implicated a loan without a bundle (or a clean loan an incidental cross-rule touched that isn't in ground truth) — the fix is in the rule, never in the assertion.
