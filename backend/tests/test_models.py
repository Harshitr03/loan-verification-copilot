import pytest
from decimal import Decimal
from backend.app.models import Loan, Exception as Exc, AuditEntry


@pytest.mark.asyncio
async def test_can_insert_and_query_loan(db):
    await Loan(loan_id="LN1", dataset_id="D1", original_principal=Decimal("100.00"),
              validation_status="pending", lifecycle_state="imported").insert()
    got = await Loan.find_one(Loan.loan_id == "LN1")
    assert got is not None and got.original_principal == Decimal("100.00")


@pytest.mark.asyncio
async def test_exception_bundle_shape(db):
    e = Exc(loan_id="LN1", dataset_id="D1", rule_id="interest_rate_range", type="ROW",
            severity="medium", source="rule", field="interest_rate",
            observed_value="99", expected="2-36", message="out of band", status="open")
    await e.insert()
    assert (await Exc.find_one(Exc.rule_id == "interest_rate_range")).field == "interest_rate"
