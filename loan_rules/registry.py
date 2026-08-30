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
