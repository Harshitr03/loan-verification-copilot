from datetime import datetime, timezone
from typing import Optional
from beanie import Document
from pydantic import Field


class AIRecommendation(Document):
    exception_id: Optional[str] = None
    loan_id: Optional[str] = None
    kind: str                                # explain|suggest|compare|notes|classify|summarize|generate_rule
    provider: str
    model: str
    prompt: str
    response: str
    suggested_value: Optional[str] = None
    confidence: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    decision: str = "pending"                # pending | accepted | edited | rejected
    decided_by: Optional[str] = None
    decided_at: Optional[datetime] = None

    class Settings:
        name = "ai_recommendations"
