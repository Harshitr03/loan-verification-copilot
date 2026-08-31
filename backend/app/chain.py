import hashlib
from datetime import datetime, timezone
from backend.app.canonical import canonical_json
from backend.app.models import Counter


class HashChain:
    def __init__(self, model, name, *, prev_field="prev_hash",
                 hash_field="entry_hash", ts_field="timestamp"):
        self.model, self.name = model, name
        self.prev_field, self.hash_field, self.ts_field = prev_field, hash_field, ts_field

    async def next_seq(self) -> int:
        doc = await Counter.get_motor_collection().find_one_and_update(
            {"_id": self.name}, {"$inc": {"value": 1}}, upsert=True, return_document=True)
        return doc["value"]

    async def _tail(self):
        t = await self.model.find().sort(-self.model.seq).limit(1).to_list()
        return t[0] if t else None

    def _hash(self, prev_hash, seq, ts_iso, domain):
        body = {"seq": seq, "ts_iso": ts_iso, **domain}
        return hashlib.sha256((prev_hash + canonical_json(body)).encode()).hexdigest()

    async def append(self, **domain):
        seq = await self.next_seq()
        tail = await self._tail()
        prev_hash = getattr(tail, self.hash_field) if tail else ""
        now = datetime.now(timezone.utc)
        ts_iso = now.isoformat()
        h = self._hash(prev_hash, seq, ts_iso, domain)
        doc = self.model(seq=seq, ts_iso=ts_iso,
                         **{self.ts_field: now, self.prev_field: prev_hash, self.hash_field: h},
                         **domain)
        await doc.insert()
        return doc

    async def verify(self) -> dict:
        meta = {"id", "revision_id", "seq", "ts_iso",
                self.ts_field, self.prev_field, self.hash_field}
        prev_hash = ""
        async for e in self.model.find().sort(+self.model.seq):
            d = {k: v for k, v in e.model_dump().items() if k not in meta}
            if getattr(e, self.prev_field) != prev_hash or \
               getattr(e, self.hash_field) != self._hash(prev_hash, e.seq, e.ts_iso, d):
                return {"ok": False, "broken_at": e.seq}
            prev_hash = getattr(e, self.hash_field)
        return {"ok": True, "broken_at": None}
