from decimal import Decimal
from typing import Annotated
from bson import Decimal128
from pydantic import BeforeValidator


def _to_decimal(v):
    # Beanie stores Decimal as BSON Decimal128; pydantic v2 won't re-validate that
    # back into a Decimal field, so coerce on the way in.
    if isinstance(v, Decimal128):
        return v.to_decimal()
    return v


Money = Annotated[Decimal, BeforeValidator(_to_decimal)]
