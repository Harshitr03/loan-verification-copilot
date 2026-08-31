from backend.app.ai.base import AIProvider, AIResult
from backend.app.ai.mock import MockProvider


class ClaudeProvider(AIProvider):
    provider = "claude"
    model = "claude-sonnet-5"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._mock = MockProvider()      # reused for deterministic suggested_value/severity

    def _message(self, system: str, user: str) -> str:
        # isolated seam (monkeypatched in tests); imports anthropic lazily
        import anthropic
        client = anthropic.Anthropic(api_key=self.api_key)
        msg = client.messages.create(model=self.model, max_tokens=512,
                                     system=system, messages=[{"role": "user", "content": user}])
        return msg.content[0].text

    def _op(self, kind, payload, base: AIResult) -> AIResult:
        text = self._message(
            f"You are a loan-data validation assistant. Task: {kind}. "
            f"Be concise and never fabricate values.", str(payload))
        return AIResult(kind=kind, text=text, suggested_value=base.suggested_value,
                        confidence=base.confidence, provider=self.provider,
                        model=self.model, prompt=str(payload))

    def explain(self, b): return self._op("explain", b, self._mock.explain(b))
    def suggest(self, b): return self._op("suggest", b, self._mock.suggest(b))
    def compare(self, b): return self._op("compare", b, self._mock.compare(b))
    def notes(self, b): return self._op("notes", b, self._mock.notes(b))
    def classify(self, b): return self._op("classify", b, self._mock.classify(b))
    def summarize(self, bs): return self._op("summarize", bs, self._mock.summarize(bs))
    def generate_rule(self, t): return self._op("generate_rule", {"text": t}, self._mock.generate_rule(t))
