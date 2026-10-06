from decimal import Decimal
from api.platform.postgres import QueryBuilder


def test_serialize_keeps_decimal():
    out = QueryBuilder._serialize({"amount": Decimal("12.10")})
    assert out["amount"] == Decimal("12.10") and isinstance(out["amount"], Decimal)
