import json
from collections import Counter
from backend.app.ai.base import AIProvider, AIResult

_SEVERITY = {"required_fields": "high", "closed_with_balance": "high",
             "non_negative_amounts": "high", "balance_le_principal": "high",
             "valid_dates": "high", "maturity_after_origination": "high",
             "duplicate_loan_id": "high", "interest_rate_range": "medium",
             "valid_state_code": "medium", "payment_status_vs_dpd": "medium",
             "source_conflict": "medium", "document_status_present": "medium",
             "duplicate_borrower_combo": "medium", "stale_record": "low",
             "suspicious_borrower_repeat": "low"}


class MockProvider(AIProvider):
    provider = "mock"
    model = "mock-1"

    def _r(self, kind, text, sv=None, conf=0.0):
        return AIResult(kind=kind, text=text, suggested_value=sv, confidence=conf,
                        provider=self.provider, model=self.model)

    def explain(self, b):
        return self._r("explain",
                       f"Field '{b.get('field')}' failed rule '{b.get('rule_id')}': "
                       f"observed {b.get('observed_value')!r}, expected {b.get('expected')!r}. "
                       f"{b.get('message', '')}".strip())

    def suggest(self, b):
        rid = b.get("rule_id")
        sv = {
            "interest_rate_range": "6.0",
            "valid_state_code": "CA",
            "closed_with_balance": "0.00",
            "non_negative_amounts": "0.00",
            "payment_status_vs_dpd": "0",
        }.get(rid)
        if sv is None and b.get("sibling_value") is not None:
            sv = str(b.get("sibling_value"))
        if sv is None:
            sv = str(b.get("expected") or "")
        return self._r("suggest", f"Suggest setting {b.get('field')} to {sv}.", sv=sv, conf=0.6)

    def compare(self, b):
        sib = b.get("sibling_value")
        return self._r("compare",
                       f"servicer_update reports {sib!r} vs loan value {b.get('observed_value')!r}; "
                       f"the servicer record is the more reliable source.",
                       sv=(str(sib) if sib is not None else None), conf=0.65)

    def notes(self, b):
        return self._r("notes",
                       f"Reviewer note: exception '{b.get('rule_id')}' on field "
                       f"'{b.get('field')}' requires attention before verification.")

    def classify(self, b):
        sev = _SEVERITY.get(b.get("rule_id"), "medium")
        return self._r("classify", f"Recommended severity: {sev}.", sv=sev, conf=0.7)

    def summarize(self, bundles):
        c = Counter(x.get("rule_id") for x in bundles)
        body = "; ".join(f"{k}: {v}" for k, v in sorted(c.items())) or "no exceptions"
        return self._r("summarize", f"{len(bundles)} exceptions — {body}.", conf=0.9)

    def generate_rule(self, text):
        candidate = {"id": "custom_rule", "params": {}, "enabled": False, "_from_nl": text}
        return self._r("generate_rule", json.dumps(candidate, sort_keys=True))
