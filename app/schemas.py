from datetime import date
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_TXN = Decimal("1000000.00")
MAX_QUOTA = Decimal("10000000.00")


def money_str(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"


def check_two_decimals(v: Decimal) -> Decimal:
    if v.as_tuple().exponent < -2:
        raise ValueError("at most two decimals")
    return v


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SellerIn(StrictModel):
    seller_id: str = Field(pattern=r"^S[0-9]{5}$")
    name: str = Field(min_length=1, max_length=80)
    store_id: str

    @field_validator("name")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be blank")
        return v


class SellerPatch(StrictModel):
    status: Literal["ACTIVE", "INACTIVE"]


class SellerOut(BaseModel):
    seller_id: str
    name: str
    store_id: str
    status: str


class QuotaIn(StrictModel):
    amount: Decimal

    @field_validator("amount")
    @classmethod
    def valid_amount(cls, v: Decimal) -> Decimal:
        check_two_decimals(v)
        if v <= 0 or v > MAX_QUOTA:
            raise ValueError("quota must be > 0 and <= 10,000,000.00")
        return v


class CreditIn(StrictModel):
    seller_id: str
    split_pct: int = Field(ge=1, le=100)


class TransactionIn(StrictModel):
    transaction_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,32}$")
    type: Literal["SALE", "RETURN"]
    txn_date: date
    store_id: str
    amount: Decimal
    credits: Optional[List[CreditIn]] = None
    original_transaction_id: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def valid_amount(cls, v: Decimal) -> Decimal:
        check_two_decimals(v)
        if v <= 0 or v > MAX_TXN:
            raise ValueError("amount must be > 0 and <= 1,000,000.00")
        return v


class ImportIn(StrictModel):
    transactions: List[TransactionIn] = Field(min_length=1, max_length=5000)
