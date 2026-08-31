# Synthetic Data Generator — Design Spec

**Project:** Intain Campus FinTech Challenge 2026 — Full Stack Track
**Component:** Organizer data package generator + the shared Rule spine
**Date:** 2026-08-29
**Status:** Draft for review
**Parent spec:** [2026-08-27-loan-verification-copilot-design.md](./2026-08-27-loan-verification-copilot-design.md)

---

## 1. Purpose

The public loan-level sources named in the problem statement (Fannie Mae,
Freddie Mac) are registration-gated, carry a mortgage-*performance* schema
unrelated to our 21-field canonical schema, and — being curated — contain none
of the 15 intentional data issues our validation engine is graded on catching.

This generator produces a **synthetic, public-modeled** organizer package
instead: a realistic loan tape whose clean rows satisfy every validation rule by
construction, into which we inject the 15 issue types at controlled rates with a
recorded ground-truth map. Because we know exactly which defect sits on which
row, the package doubles as the test oracle for the validation engine.

**Design center — one rule, two directions.** Injection and detection are the
same 15 rules. Hand-coding them twice (a `corrupt` in the generator, a `check` in
the engine) guarantees drift, and when they drift the oracle silently lies. So
the spine of this design is a single self-describing `Rule` object that carries
*both* directions, colocated, reading one set of params. The generator, the
engine, and Module D's LLM-context builder are three consumers of the same 15
rule definitions.

Scope here: the `Rule` object, the generator that drives it, and the package it
emits. The engine and Module D consume the same rules but are specified in the
parent spec.

---

## 2. Outputs

All files written to `data/`:

| File | Purpose |
|---|---|
| `loan_tape.csv` | Primary dataset — ~5,000 rows (5,000 base + a small injected repeat cluster, see §5), 21 canonical fields |
| `servicer_update.csv` | Second-source update file; ~40% coverage, a subset conflicting |
| `document_manifest.csv` | Document availability by loan ID; ~5% of loans absent |
| `validation_rules.json` | Configurable params for all 15 rules (single source of truth) |
| `users.json` | Three seeded users (operator/reviewer/consumer), hashed passwords |
| `expected_exception_sample.csv` | Brief's small orientation sample (~25 rows) |
| `ground_truth_exceptions.csv` | **Every** injected defect — the test oracle (byproduct of `.corrupt`) |

`ground_truth_exceptions.csv` is the one addition beyond the brief's file list
(§5). It is a *byproduct* of injection, not a curated file: every call to a rule's
`.corrupt` appends its bundle.

---

## 3. The Rule object — the shared spine

One dataclass, defined in a **standalone top-level package** — `loan_rules/`, a
package in its own right, *not* nested under `backend/app/` — so that importing it
does not execute `backend/app/__init__.py` or `backend/app/validation/__init__.py`
(either of which will pull `config`/Beanie/Motor and destroy purity). The entire
package chain down to the rules is guaranteed side-effect-free: `loan_rules/__init__.py`
imports nothing but the rule definitions themselves. Both the engine and the
generator depend on `loan_rules`; neither depends on the other.

**Cross-tree import mechanism (so `make seed` doesn't `ModuleNotFoundError`):**
`loan_rules` is installed as an editable package (`pip install -e .` via the repo's
`pyproject.toml`), and both `data/generate.py` and the backend import it as a normal
top-level module. No `sys.path` hacking.

```python
class Scope(enum.Enum):
    ROW = "row"          # judged on one loan in isolation
    DATASET = "dataset"  # needs cross-record / cross-file context

@dataclass(frozen=True)
class Rule:
    id: str                                        # identity; the only compared field
    scope: Scope = field(compare=False)
    severity: str = field(compare=False)
    params: Mapping = field(compare=False)         # from validation_rules.json (immutable view)
    message_tmpl: str = field(compare=False)       # one template -> engine msg, sample, LLM seed
    check:   Callable = field(compare=False)       # detect a violation
    corrupt: Callable = field(compare=False)       # manufacture a violation
    profiles: frozenset[str] = field(default=frozenset({"loan_tape"}), compare=False)
```

`params` is a read-only `Mapping` (a `MappingProxyType` over the loaded JSON) so
`frozen=True` isn't silently undermined by a mutable `dict`. **Every field except
`id` is `compare=False`**, so `Rule` hashes and compares by `id` alone — the
`MappingProxyType` `params` (unhashable) and the `Callable`s are excluded from
`__hash__`, which is what lets us key/set on rules. (The implementation plan Task 1
verifies this.)

**`profiles`** (parent spec §6.1/§7) is a `frozenset[str]` naming the dataset
profiles a rule applies to. It **defaults to `{"loan_tape"}`** (the graded path), so
the 7 `loan_tape`-only rules need no override; the 8 row-local rules pass
`profiles={"loan_tape", "sf_performance_panel"}`. The generator only ever produces the
**`loan_tape`** profile, so it drives *all 15* rules' `corrupt`; `profiles` is consumed
downstream by the panel-consistency pass (parent §6.2) to run only the 8 row-local
rules on loan-month data. Being last with a default keeps every existing `Rule(...)`
call valid.

**Signatures are symmetric across scope** — this is what keeps the two loops
reusable instead of special-cased:

| Scope | `check` | `corrupt` |
|---|---|---|
| `ROW` | `(loan, params) -> Exception \| None` | `(loan, rng, params) -> (loan', bundle)` |
| `DATASET` | `(dataset, ctx, params) -> list[Exception]` | `(dataset, rng, params) -> (dataset', list[bundle])` |

**`check` and `corrupt` are pure functions that take `params` explicitly** (see the
signatures above) — they do *not* close over it. `params` is loaded from
`validation_rules.json` once and stored in exactly one place, the `Rule.params`
field; every call site threads that single object in (`rule.check(loan, rule.params)`).
This keeps the callables trivially unit-testable and guarantees injection and
detection read the *same* thresholds from the *same* object — there is no second
copy to drift.

- **Generator** iterates the rules, calls `.corrupt`.
- **Engine** iterates the same rules, calls `.check`.
- **Module D** renders `message_tmpl` and reads the bundle (§7) for LLM grounding.

### Row-scoped vs dataset-scoped

Three issues — duplicate loan id (2), duplicate borrower+amount+orig-date combo
(3), suspiciously repeated borrower (14) — are not a property of one row; they
cannot fit a `corrupt(loan)` / `check(loan)` signature. They are `DATASET` scope:
`corrupt` mutates the dataset (copies an id, clones a combo, adds repeated-borrower
rows) and `check` runs against the cross-record context the parent spec already
requires (duplicate index, servicer/manifest joins). Making the asymmetry explicit
and symmetric on both sides is what lets one loop drive all 15 rules.

---

## 4. Base tape — internally consistent clean rows

The ~90% clean rows are *correlated the way real loans are*, not independently
random. This makes injected defects genuine anomalies (and gives the Phase-2 ML
layer real signal). Invariants held by every clean row — i.e. every rule's
`.check` returns `None`:

- `maturity_date = origination_date + term_months`
- `current_balance ≤ original_principal`
- `interest_rate` drawn from a band keyed to `credit_grade` (better grade → lower rate)
- `days_past_due` consistent with `payment_status` (`CURRENT` → 0 DPD;
  `DELINQUENT` → positive DPD; `CLOSED` → 0 balance)
- `borrower_state` ∈ valid 2-letter US codes
- `origination_date` in a plausible historical window
- `last_updated_at` within the staleness window
- realistic enums for `loan_type`, `loan_purpose`, `income_band`, `servicer_name`,
  `source_system`, `document_status`

Field domains and enum vocabularies are fixed constants in the generator and
mirror the canonical schema in the parent spec (§4).

---

## 5. Defect allocation — one solved plan, not competing knobs

Three constraints — ~10% of rows defective, ≤2 defects per row, ~30–40 instances
per type — cannot be run as independent loops (they deadlock: targets unmet, or
the per-row cap exceeded). Model them as **one allocation**:

0. **Only enabled rules are injected.** A rule disabled in `validation_rules.json`
   is skipped by the generator *and* the engine, so injection and detection stay in
   lockstep (a disabled rule with an injected defect would have no `check` and fail
   the round-trip and superset oracle). The generator and engine filter on the same
   flag from the same file.
1. Build a **defect plan**: a flat list of type-assignments sized by per-type
   target for enabled rules (~15 types × ~35 ≈ ~525 assignments).
2. Shuffle assignments into rows respecting the ≤2 cap. `DATASET`-scope assignments
   (2, 3, 14) go through their own `.corrupt` (see below) rather than a single-row
   slot.
3. If the targets don't fit under the cap, **grow the defective set** rather than
   silently under-filling. One solved allocation, checked feasible up front.

For each assignment, call the rule's `.corrupt`, which returns the mutated
record(s) and one or more **defect context bundles** (§7). Those bundles, appended
across all assignments, *are* `ground_truth_exceptions.csv`.

### The defective set is defined by ground truth, not by mutation

The engine's unit of exception is *any `loan_id` implicated by a defect in any
file* — not just the tape row the generator happened to mutate. A DATASET rule
routinely flags a **partner** loan that was never corrupted:

- `duplicate_loan_id` / `duplicate_borrower_combo`: the engine flags *both* members
  of the collision, including the pre-existing original.
- `suspicious_borrower_repeat`: every member of the repeated-borrower group is
  flagged, not just the ones added.
- `source_conflict`: the corruption lives in `servicer_update.csv`, but the
  exception attaches to the *tape* loan, whose own row is otherwise clean.

So **the defective set ≡ the set of `loan_id`s appearing in
`ground_truth_exceptions.csv`**, and every rule's `.corrupt` emits a bundle for
*every* loan it implicates — including the unmutated partner. A partner's bundle
has `observed_value == original_value` (nothing changed on its row; it is flagged
by *relationship*), and its `field`/`message` describe the collision. This is what
makes the superset oracle and the "no clean loan is flagged" check (§10.3) both
hold on a correct engine.

### DATASET corruption mechanics (fixed row count vs the ≤2 cap)

- `duplicate_loan_id`, `duplicate_borrower_combo`: **repurpose an existing
  not-yet-defective row** — mutate it to collide with a target row rather than
  appending. Both collision members receive bundles; total row count stays 5,000.
- `suspicious_borrower_repeat`: **adds a small cluster of rows** for one borrower —
  that is the phenomenon. This is the only rule that grows the tape, hence the
  "~5,000 base + injected cluster" in §2/§4. Every clustered loan gets a bundle.
- A rule's per-type "target ~35" counts **exception-emitting loans** (bundles), not
  extra rows. Repurposed/partner rows count against neither the base 5,000 nor a
  new slot; they are already-present rows re-labelled by the corruption.

The 15 issue types → rule ids and where each is injected:

| # | Issue | Rule id | Scope | Injected in |
|---|---|---|---|---|
| 1 | Missing loan ID | `required_fields` | ROW | loan_tape (blank `loan_id`) |
| 2 | Duplicate loan ID | `duplicate_loan_id` | DATASET | loan_tape (copy an existing id) |
| 3 | Duplicate borrower+amount+orig-date | `duplicate_borrower_combo` | DATASET | loan_tape |
| 4 | Invalid date format | `valid_dates` | ROW | loan_tape (e.g. `13/40/2020`) |
| 5 | Maturity before origination | `maturity_after_origination` | ROW | loan_tape |
| 6 | Negative principal/balance | `non_negative_amounts` | ROW | loan_tape |
| 7 | Balance > principal | `balance_le_principal` | ROW | loan_tape |
| 8 | Interest rate out of range | `interest_rate_range` | ROW | loan_tape |
| 9 | Payment status vs DPD mismatch | `payment_status_vs_dpd` | ROW | loan_tape |
| 10 | Missing document status | `document_status_present` | DATASET | manifest (loan absent) |
| 11 | Conflicting tape vs servicer | `source_conflict` | DATASET | servicer_update (divergent value) |
| 12 | Stale record | `stale_record` | ROW | loan_tape (old `last_updated_at`) |
| 13 | Invalid state code | `valid_state_code` | ROW | loan_tape (`ZZ`, `XX`) |
| 14 | Suspiciously repeated borrower | `suspicious_borrower_repeat` | DATASET | loan_tape (many rows, one borrower) |
| 15 | Closed with positive balance | `closed_with_balance` | ROW | loan_tape |

### Incidental cross-rule violations — oracle is a superset, not an equality

One corruption can *incidentally* trip a second rule (a negative
`original_principal` with a positive `current_balance` also violates
`balance_le_principal`). Corruptions are authored to be single-rule where
feasible, but the oracle does **not** assert the engine finds *exactly* the
injected set. It asserts:

- every injected defect is detected (engine output ⊇ ground truth), and
- no loan **absent from `ground_truth_exceptions.csv`** produces any exception,
  evaluated in the full multi-file context (tape + servicer + manifest).

The second clause is scoped to ground-truth absence, not "unmutated row," precisely
because DATASET partners (previous subsection) are unmutated yet legitimately
flagged — they are in ground truth, so they don't violate it. This is robust to
incidental violations while still proving injection ⇒ detection.

---

## 6. Cross-file generation

Generated *after* defect selection so they can reference the same `loan_id`s:

- **`servicer_update.csv`** — one row for ~40% of tape loans. Most echo the tape
  (a benign later update: slightly lower balance, newer `last_payment_date`). The
  `source_conflict` (11) targets instead carry a value in `current_balance`,
  `interest_rate`, or `payment_status` that contradicts the tape. The conflicting
  servicer value is recorded as the bundle's `sibling_value`.
- **`document_manifest.csv`** — one row per loan (`loan_id` + `document_status`),
  **except** the `document_status_present` (10) targets, deliberately omitted.

---

## 7. The defect context bundle — one shape, reused

`.corrupt` emits, and `.check` (for injected data) reconstructs, a minimal bundle.
It is deliberately *small* — the LLM grounds on `{field, value, band}`, never a
21-column row dump plus cross-file join it has to sift. This is the concrete
"managing LLM context" win: the generator, by defining the minimal bundle up
front, forces every downstream consumer to the same tight grounding.

```
{ loan_id, rule_id, field, observed_value, expected /* params */,
  sibling_value?,   # servicer_update value, for source_conflict
  message }         # rendered from Rule.message_tmpl
```

Reused three ways:

- **Generator** writes it (plus an oracle-only `original_value`) as
  `ground_truth_exceptions.csv`.
- **Engine** `Exception` is this shape (aligns with parent §5's existing
  `observed_value` / `expected` fields).
- **Module D** `build_context(exception)` returns *only* these fields as the LLM
  grounding.

**Naming:** the bundle field carrying the injected/observed bad value is
`observed_value` everywhere — bundle, `ground_truth_exceptions.csv` column, engine
`Exception`, and prose. The generator additionally records an oracle-only
`original_value` (the pre-corruption value); there is no `corrupted_value` term.

**One honest caveat:** a *detected* exception on real uploaded data has no
"before," so `original_value` is generator-only. The shape shared across all three
consumers is the intersection above; the generator merely records that one extra
column for its own oracle. `message_tmpl` renders one message
that seeds the engine exception, the human-readable `expected_exception_sample.csv`
message, and the LLM explanation — one template, not three copies.

---

## 8. Config files

- **`validation_rules.json`** — the single source of params: interest-rate band
  (e.g. 2–36%), staleness window (e.g. 180 days), severity per rule,
  enable/disable flags. Loaded once into each `Rule.params` (a read-only mapping),
  so the value used to inject and the value used to detect come from one object.
  The **enable/disable flag is honoured by both** the generator (won't inject a
  disabled rule) and the engine (won't check it) — see §5 step 0 — so the two never
  fall out of lockstep.
- **`users.json`** — three users (`operator`/Data Operator, `reviewer`/Reviewer,
  `consumer`/Data Consumer). Passwords bcrypt-hashed; plaintext test credentials
  documented in the README (deliverables §13). See §9 for why this file is
  excluded from the reproducibility hash.

---

## 9. Implementation shape & RNG discipline

- `data/generate.py` — single seeded script. Deps: `numpy`, `faker`, stdlib
  `csv`/`json`, `bcrypt`. Imports the `Rule` set from the standalone `loan_rules`
  package (editable-installed, §3) — not via a `backend/app/...` path.
- CLI: `--rows` (5000), `--defect-rate` (0.10), `--seed` (fixed default),
  `--out-dir` (`data/`). Run via `make seed`.
- **RNG — two independent generators, both seeded from `--seed`:**
  - one `numpy.random.Generator` for all numeric/date/choice draws, giving each
    rule a **spawned sub-stream** (`rng.spawn`, NumPy ≥1.25) so adding/removing a
    rule doesn't reshuffle every other row's randomness — hash-equal fixtures stay
    stable as the rule set evolves.
  - **Faker does not draw from numpy** — it has its own `random.Random`. It is
    seeded separately via `Faker.seed_instance(seed)` (using the same `--seed`),
    otherwise names/addresses differ every run and reproducibility fails on
    `loan_tape.csv`, not just `users.json`.
- **Byte-reproducibility also requires stable serialization:** fixed float
  formatting (e.g. `Decimal` with a fixed quantize, or a pinned `f"{x:.2f}"`), a
  fixed column order, and `json.dump(..., sort_keys=True)`. The reproducibility
  test (§10.1) asserts these hold.

---

## 10. Testing (TDD — tests before `generate.py`)

The headline test the shared `Rule` object buys us, per rule:

```python
for rule in ROW_RULES:
    clean = make_clean_row(rule)
    corrupted, _bundle = rule.corrupt(clean, rng, rule.params)
    assert rule.check(corrupted, rule.params) is not None   # injection is detectable
    assert rule.check(clean,     rule.params) is None        # clean stays clean
```

**The DATASET round-trip — where the real bugs live — needs a cross-file harness,**
not a single row. `corrupt` mutates a *dataset* and returns bundles for every
implicated loan; `check` runs against the built context (duplicate index,
servicer/manifest joins). The assertion is set-based:

```python
for rule in DATASET_RULES:
    ds = make_clean_dataset()                       # tape + servicer + manifest
    ds2, bundles = rule.corrupt(ds, rng, rule.params)
    ctx = build_context(ds2)                        # duplicate index + joins
    flagged = {e.loan_id for e in rule.check(ds2, ctx, rule.params)}
    implicated = {b.loan_id for b in bundles}
    assert implicated <= flagged                    # every implicated loan is caught,
                                                    # incl. the unmutated partner (§5)
    assert not rule.check(make_clean_dataset(), build_context(...), rule.params)
```

Together these prove oracle and engine agree per rule, with no hand-maintained
ground truth. Additional assertions:

1. **Reproducibility** — two runs at the same seed produce identical files, hashed
   over the CSV/JSON outputs **excluding `users.json`** (bcrypt salts are random per
   call, so `users.json` is not byte-reproducible; usernames/roles asserted
   structurally instead). This depends on the stable-serialization rules in §9
   (fixed float repr, fixed column order, `sort_keys`) — the test fails if any drift.
2. **Type coverage** — every enabled rule id appears in `ground_truth_exceptions.csv`
   at ≥ its target count.
3. **Superset oracle** — every injected defect is present in engine output; **no
   loan absent from `ground_truth_exceptions.csv` yields any exception**, evaluated
   in full multi-file context (§5).
4. **Cross-file linkage** — every `servicer_update`/`manifest` `loan_id` resolves
   to a tape loan; omitted-from-manifest loans equal the type-10 target set;
   `source_conflict` sibling values differ from the tape; and both members of every
   duplicate collision appear in ground truth.

---

## 11. Trade-offs

- **One `Rule` object over two parallel implementations:** the whole point — 15
  definitions consumed by three call sites instead of ~30 drifting functions. The
  round-trip test is only possible because `check` and `corrupt` are colocated on
  one params source.
- **Superset oracle over exact match:** robust to incidental cross-rule
  violations; still proves injection ⇒ detection.
- **Synthetic over public data:** lose real provenance, gain known ground truth, a
  matching schema, and guaranteed presence of all 15 defect types with no
  registration walls.
- **Correlated base data over independent draws:** more generation code, but
  defects become true anomalies and the ML layer gains signal.
- **Spawned RNG sub-streams over a single stream:** stable fixtures as the rule set
  evolves, at the cost of threading a sub-stream per rule.

---

## 12. Parent-spec ripple (to reconcile next)

Adopting the `Rule` spine changes the parent spec:

- **§7 (Validation Engine):** "each rule is a small pure function `(loan, ctx) ->
  Exception | None`" becomes "each rule is a `Rule` object carrying pure `check` +
  `corrupt` (both taking `params` explicitly) + severity + `message_tmpl`, `ROW` or
  `DATASET` scoped." The engine imports rules from `loan_rules`.
- **§14 (Repo layout):** add a **standalone top-level `loan_rules/` package** (the
  shared spine, import-pure, editable-installed), imported by both `backend/app/`
  and `data/generate.py`. It does **not** live under `backend/app/validation/`.
  Add a `pyproject.toml` for the editable install.
- **§5 (Exceptions collection):** confirm the `Exception` fields are exactly the
  §7 bundle here — `observed_value`/`expected`/`sibling_value?` — with no
  `corrupted_value`.

**Status: applied** to `2026-08-27-loan-verification-copilot-design.md` (§5 exceptions
shape, §7 validation-engine `Rule`-object framing, §14 repo layout with the standalone
`loan_rules/` package + `pyproject.toml`).
