from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import BigInteger, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Store(SQLModel, table=True):
    store_id: str = Field(primary_key=True, max_length=8)
    zone: str
    format: str
    distribution_center: str
    sales_floor_m2: int


class Seller(SQLModel, table=True):
    seller_id: str = Field(primary_key=True, max_length=6)
    name: str = Field(max_length=80)
    store_id: str = Field(foreign_key="store.store_id")
    status: str = Field(default="ACTIVE", max_length=8)
    created_at: datetime = Field(default_factory=utcnow)


class Period(SQLModel, table=True):
    period_id: str = Field(primary_key=True, max_length=7)
    start_date: date
    end_date: date
    status: str = Field(default="OPEN", max_length=6)
    closed_at: Optional[datetime] = None


class Quota(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("period_id", "seller_id"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    period_id: str = Field(foreign_key="period.period_id")
    seller_id: str = Field(foreign_key="seller.seller_id")
    amount_cents: int = Field(sa_column=Column(BigInteger, nullable=False))
    updated_at: datetime = Field(default_factory=utcnow)


class Txn(SQLModel, table=True):
    __tablename__ = "txn"
    transaction_id: str = Field(primary_key=True, max_length=32)
    type: str = Field(max_length=6)
    txn_date: date
    store_id: str = Field(foreign_key="store.store_id")
    amount_cents: int = Field(sa_column=Column(BigInteger, nullable=False))
    original_transaction_id: Optional[str] = Field(default=None, foreign_key="txn.transaction_id")
    period_id: str = Field(foreign_key="period.period_id")
    created_at: datetime = Field(default_factory=utcnow)


class Credit(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("transaction_id", "seller_id"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    transaction_id: str = Field(foreign_key="txn.transaction_id")
    seller_id: str = Field(foreign_key="seller.seller_id")
    line_no: int
    split_pct: int
    credit_cents: int = Field(sa_column=Column(BigInteger, nullable=False))
    period_id: str = Field(foreign_key="period.period_id")
    created_at: datetime = Field(default_factory=utcnow)


class Payout(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("period_id", "seller_id"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    period_id: str = Field(foreign_key="period.period_id")
    seller_id: str = Field(foreign_key="seller.seller_id")
    quota_cents: int = Field(sa_column=Column(BigInteger, nullable=False))
    credited_cents: int = Field(sa_column=Column(BigInteger, nullable=False))
    attainment_pct: str = Field(max_length=16)
    qualified: bool
    payout_cents: int = Field(sa_column=Column(BigInteger, nullable=False))
    calculated_at: datetime = Field(default_factory=utcnow)
