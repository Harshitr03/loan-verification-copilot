from backend.app.chain import HashChain
from backend.app.models import VerifiedRecord
from data._serialize import CANONICAL_COLUMNS, format_value

_chain = HashChain(VerifiedRecord, "verified", prev_field="prev_record_hash",
                   hash_field="record_hash", ts_field="verified_at")


def _serialize_canonical(loan) -> dict:
    # string-serialized (BSON-stable) canonical view, so the hashed record survives
    # a real-Mongo round-trip (P1 domain-stability rule)
    return {c: format_value(getattr(loan, c, None)) for c in CANONICAL_COLUMNS}


async def build_verified_record(loan, reviewer, ai_ref=None) -> VerifiedRecord:
    return await _chain.append(
        loan_id=loan.loan_id,
        canonical_data=_serialize_canonical(loan),
        source_file_ref=loan.dataset_id,
        validation_result={"status": loan.validation_status},
        reviewer_decision=None,
        ai_recommendation_ref=ai_ref,
        verified_by=reviewer,
    )
