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
