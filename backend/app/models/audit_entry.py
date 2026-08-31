from datetime import datetime
from beanie import Document
from pydantic import Field
import pymongo


class AuditEntry(Document):
    seq: int
    event_type: str
    entity_type: str
    entity_id: str
    actor: str
    payload: dict = Field(default_factory=dict)
    prev_hash: str = ""
    entry_hash: str = ""
    ts_iso: str                              # hashed timestamp string
    timestamp: datetime                      # queryable datetime (unhashed)

    class Settings:
        name = "audit_log"
        indexes = [[("seq", pymongo.ASCENDING)]]
