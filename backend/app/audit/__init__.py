from backend.app.chain import HashChain
from backend.app.models import AuditEntry

_chain = HashChain(AuditEntry, "audit")   # ts_field defaults to "timestamp"


async def append(event_type, entity_type, entity_id, actor, payload: dict):
    return await _chain.append(event_type=event_type, entity_type=entity_type,
                               entity_id=entity_id, actor=actor, payload=payload)


async def verify_chain() -> dict:
    return await _chain.verify()
