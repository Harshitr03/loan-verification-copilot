from abc import ABC, abstractmethod
from dataclasses import dataclass

KINDS = ("explain", "suggest", "compare", "notes", "classify", "summarize", "generate_rule")


@dataclass
class AIResult:
    kind: str
    text: str
    suggested_value: str | None = None
    confidence: float = 0.0
    provider: str = ""
    model: str = ""
    prompt: str = ""


class AIProvider(ABC):
    @abstractmethod
    def explain(self, bundle: dict) -> AIResult: ...
    @abstractmethod
    def suggest(self, bundle: dict) -> AIResult: ...
    @abstractmethod
    def compare(self, bundle: dict) -> AIResult: ...
    @abstractmethod
    def notes(self, bundle: dict) -> AIResult: ...
    @abstractmethod
    def classify(self, bundle: dict) -> AIResult: ...
    @abstractmethod
    def summarize(self, bundles: list[dict]) -> AIResult: ...
    @abstractmethod
    def generate_rule(self, text: str) -> AIResult: ...
