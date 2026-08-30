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
