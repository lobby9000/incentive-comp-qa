from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlmodel import Session, select

from .calc import calculate, display
from .errors import ApiError
from .models import Credit, Payout, Period, Quota, Seller, Store, Txn
from .schemas import TransactionIn, money_str

CLAWBACK_DAYS = 30


def to_cents(amount: Decimal) -> int:
    return int(amount * 100)


# ---------------------------------------------------------------- lookups

def get_period(session: Session, period_id: str) -> Period:
    period = session.get(Period, period_id)
    if period is None:
        raise ApiError(404, "PERIOD_NOT_FOUND", f"Period {period_id} does not exist")
    return period


def get_seller(session: Session, seller_id: str) -> Seller:
    seller = session.get(Seller, seller_id)
    if seller is None:
        raise ApiError(404, "SELLER_NOT_FOUND", f"Seller {seller_id} does not exist")
    return seller


def period_for_date(session: Session, d) -> Period:
    period = session.exec(
        select(Period).where(Period.start_date <= d, Period.end_date >= d)
    ).first()
    if period is None:
        raise ApiError(422, "OUT_OF_PLAN", f"{d} is outside the plan periods")
    return period


# ---------------------------------------------------------------- sellers

def create_seller(session: Session, data) -> Seller:
    if session.get(Store, data.store_id) is None:
        raise ApiError(422, "UNKNOWN_STORE", f"Store {data.store_id} does not exist")
    if session.get(Seller, data.seller_id) is not None:
        raise ApiError(409, "DUPLICATE_SELLER", f"Seller {data.seller_id} already exists")
    seller = Seller(seller_id=data.seller_id, name=data.name, store_id=data.store_id)
    session.add(seller)
    session.commit()
    session.refresh(seller)
    return seller


def update_seller(session: Session, seller_id: str, data) -> Seller:
    seller = get_seller(session, seller_id)
    seller.status = data.status
    session.add(seller)
    session.commit()
    session.refresh(seller)
    return seller


# ---------------------------------------------------------------- quotas

def set_quota(session: Session, period_id: str, seller_id: str, amount: Decimal):
    period = get_period(session, period_id)
    get_seller(session, seller_id)
    if period.status == "CLOSED":
        raise ApiError(409, "PERIOD_CLOSED", f"Period {period_id} is closed")
    quota = session.exec(
        select(Quota).where(Quota.period_id == period_id, Quota.seller_id == seller_id)
    ).first()
    created = quota is None
    if created:
        quota = Quota(period_id=period_id, seller_id=seller_id, amount_cents=to_cents(amount))
    else:
        quota.amount_cents = to_cents(amount)
        quota.updated_at = datetime.now(timezone.utc)
    session.add(quota)
    session.commit()
    session.refresh(quota)
    return quota, created


# ---------------------------------------------------------------- transactions

def split_cents(amount_cents: int, splits: list[int]) -> list[int]:
    if len(splits) == 1:
        return [amount_cents]
    second = amount_cents * splits[1] // 100
    return [amount_cents - second, second]


def build_transaction(session: Session, data: TransactionIn, pending: dict | None = None,
                      pending_credits: dict | None = None):
    """Validate one transaction and return (Txn, [Credit]) without committing.

    `pending` holds transactions already accepted earlier in the same import
    (id -> Txn) and `pending_credits` their credit lines (id -> [Credit]).
    """
    pending = pending if pending is not None else {}
    pending_credits = pending_credits if pending_credits is not None else {}

    if data.transaction_id in pending or session.get(Txn, data.transaction_id) is not None:
        raise ApiError(409, "DUPLICATE_TRANSACTION", f"Transaction {data.transaction_id} already exists")
    if session.get(Store, data.store_id) is None:
        raise ApiError(422, "UNKNOWN_STORE", f"Store {data.store_id} does not exist")

    period = period_for_date(session, data.txn_date)
    if period.status == "CLOSED":
        raise ApiError(409, "PERIOD_CLOSED", f"Period {period.period_id} is closed")

    amount_cents = to_cents(data.amount)
    credits: list[Credit] = []

    if data.type == "SALE":
        if data.original_transaction_id is not None:
            raise ApiError(422, "VALIDATION_ERROR", "A SALE cannot reference an original transaction")
        if not data.credits:
            raise ApiError(422, "VALIDATION_ERROR", "A SALE requires credits")
        if len(data.credits) > 2:
            raise ApiError(422, "VALIDATION_ERROR", "A SALE credits at most 2 sellers")
        if sum(c.split_pct for c in data.credits) != 100:
            raise ApiError(422, "INVALID_SPLIT", "Splits must add up to 100")
        ids = [c.seller_id for c in data.credits]
        if len(set(ids)) != len(ids):
            raise ApiError(422, "DUPLICATE_SELLER", "A seller appears twice in the credits")
        for c in data.credits:
            seller = session.get(Seller, c.seller_id)
            if seller is None:
                raise ApiError(422, "UNKNOWN_SELLER", f"Seller {c.seller_id} does not exist")
            if seller.status != "ACTIVE":
                raise ApiError(422, "SELLER_INACTIVE", f"Seller {c.seller_id} is inactive")
        primary = session.get(Seller, data.credits[0].seller_id)
        if primary.store_id != data.store_id:
            raise ApiError(422, "PRIMARY_SELLER_STORE_MISMATCH",
                           f"Seller {primary.seller_id} does not belong to store {data.store_id}")
        values = split_cents(amount_cents, [c.split_pct for c in data.credits])
        for i, (c, v) in enumerate(zip(data.credits, values), start=1):
            credits.append(Credit(transaction_id=data.transaction_id, seller_id=c.seller_id,
                                  line_no=i, split_pct=c.split_pct, credit_cents=v,
                                  period_id=period.period_id))
    else:
        if data.credits:
            raise ApiError(422, "CREDITS_NOT_ALLOWED", "A RETURN inherits credits from the original sale")
        if not data.original_transaction_id:
            raise ApiError(422, "UNKNOWN_ORIGINAL", "A RETURN needs original_transaction_id")
        original = pending.get(data.original_transaction_id) or session.get(Txn, data.original_transaction_id)
        if original is None:
            raise ApiError(422, "UNKNOWN_ORIGINAL",
                           f"Transaction {data.original_transaction_id} does not exist")
        if original.type != "SALE":
            raise ApiError(422, "INVALID_ORIGINAL", "Returns must reference a SALE")
        if data.txn_date < original.txn_date:
            raise ApiError(422, "RETURN_BEFORE_SALE", "Return date is earlier than the sale date")

        returned = session.exec(
            select(func.coalesce(func.sum(Txn.amount_cents), 0)).where(
                Txn.original_transaction_id == original.transaction_id)
        ).one()
        returned += sum(t.amount_cents for t in pending.values()
                        if t.original_transaction_id == original.transaction_id)
        if returned + amount_cents > original.amount_cents:
            raise ApiError(422, "RETURN_EXCEEDS_SALE", "Total returned would exceed the sale amount")

        days = (data.txn_date - original.txn_date).days
        if days < CLAWBACK_DAYS:
            orig_credits = pending_credits.get(original.transaction_id) or session.exec(
                select(Credit).where(Credit.transaction_id == original.transaction_id).order_by(Credit.line_no)
            ).all()
            splits = [c.split_pct for c in orig_credits]
            values = split_cents(-amount_cents, splits)
            for c, v in zip(orig_credits, values):
                credits.append(Credit(transaction_id=data.transaction_id, seller_id=c.seller_id,
                                      line_no=c.line_no, split_pct=c.split_pct, credit_cents=v,
                                      period_id=period.period_id))

    txn = Txn(transaction_id=data.transaction_id, type=data.type, txn_date=data.txn_date,
              store_id=data.store_id, amount_cents=amount_cents,
              original_transaction_id=data.original_transaction_id, period_id=period.period_id)
    return txn, credits


def create_transaction(session: Session, data: TransactionIn):
    txn, credits = build_transaction(session, data)
    session.add(txn)
    session.flush()  # BUG-008: the transaction row must exist before its credit lines (FK)
    for c in credits:
        session.add(c)
    session.commit()
    session.refresh(txn)
    return txn, credits


def import_transactions(session: Session, rows: list[TransactionIn]) -> dict:
    pending: dict = {}
    pending_credits: dict = {}
    built = []
    errors = []
    for i, row in enumerate(rows):
        try:
            txn, credits = build_transaction(session, row, pending, pending_credits)
        except ApiError as e:
            errors.append({"row": i, "transaction_id": row.transaction_id, "code": e.code, "message": e.message})
            continue
        pending[txn.transaction_id] = txn
        pending_credits[txn.transaction_id] = credits
        built.append((txn, credits))
    if errors:
        raise ApiError(422, "IMPORT_REJECTED", f"{len(errors)} row(s) failed; nothing was imported", errors)

    for txn, _ in built:
        session.add(txn)
    session.flush()  # BUG-008: insert every transaction before any credit line (FK)
    n_credits = 0
    for _, credits in built:
        for c in credits:
            session.add(c)
            n_credits += 1
    session.commit()
    sales = sum(1 for t, _ in built if t.type == "SALE")
    return {"imported": len(built), "sales": sales, "returns": len(built) - sales, "credits": n_credits}


# ---------------------------------------------------------------- statements and close

def credited_cents(session: Session, period_id: str, seller_id: str) -> int:
    return session.exec(
        select(func.coalesce(func.sum(Credit.credit_cents), 0)).where(
            Credit.period_id == period_id, Credit.seller_id == seller_id)
    ).one()


def statement(session: Session, period_id: str, seller_id: str) -> dict:
    period = get_period(session, period_id)
    get_seller(session, seller_id)
    quota = session.exec(
        select(Quota).where(Quota.period_id == period_id, Quota.seller_id == seller_id)
    ).first()
    if quota is None:
        raise ApiError(404, "QUOTA_NOT_FOUND", f"No quota for {seller_id} in {period_id}")

    if period.status == "CLOSED":
        payout = session.exec(
            select(Payout).where(Payout.period_id == period_id, Payout.seller_id == seller_id)
        ).first()
        result = calculate(payout.credited_cents, payout.quota_cents)
        source = "CLOSED"
    else:
        result = calculate(credited_cents(session, period_id, seller_id), quota.amount_cents)
        source = "LIVE"

    return {
        "period_id": period_id,
        "seller_id": seller_id,
        "source": source,
        "quota": f"{result.quota:.2f}",
        "net_credited": f"{result.credited:.2f}",
        "attainment_pct": f"{result.attainment_pct:.2f}",
        "qualified": result.qualified,
        "bands": [
            {
                "band": b.band,
                "from_pct": f"{b.lower_pct:.2f}",
                "to_pct": f"{b.upper_pct:.2f}",
                "rate_pct": f"{b.rate_pct:.2f}",
                "base": display(b.base),
                "commission": display(b.commission),
            }
            for b in result.bands
        ],
        "payout": f"{result.payout:.2f}",
    }


def close_period(session: Session, period_id: str) -> dict:
    period = get_period(session, period_id)
    if period.status == "CLOSED":
        raise ApiError(409, "PERIOD_ALREADY_CLOSED", f"Period {period_id} is already closed")
    earlier_open = session.exec(
        select(Period).where(Period.start_date < period.start_date, Period.status == "OPEN")
    ).first()
    if earlier_open is not None:
        raise ApiError(409, "PREVIOUS_PERIOD_OPEN", f"Close {earlier_open.period_id} first")

    quotas = session.exec(select(Quota).where(Quota.period_id == period_id)).all()
    with_quota = {q.seller_id for q in quotas}
    credited_sellers = set(session.exec(
        select(Credit.seller_id).where(Credit.period_id == period_id).distinct()
    ).all())
    missing = sorted(credited_sellers - with_quota)
    if missing:
        raise ApiError(409, "QUOTA_MISSING", "Some credited sellers have no quota", missing)

    total = 0
    rows = 0
    for q in quotas:
        c = credited_cents(session, period_id, q.seller_id)
        result = calculate(c, q.amount_cents)
        payout_cents = to_cents(result.payout)
        session.add(Payout(period_id=period_id, seller_id=q.seller_id, quota_cents=q.amount_cents,
                           credited_cents=c, attainment_pct=f"{result.attainment_pct:.2f}",
                           qualified=result.qualified, payout_cents=payout_cents))
        total += payout_cents
        rows += 1

    period.status = "CLOSED"
    period.closed_at = datetime.now(timezone.utc)
    session.add(period)
    session.commit()
    return {"period_id": period_id, "status": "CLOSED", "sellers": rows, "total_payout": money_str(total)}


def list_payouts(session: Session, period_id: str) -> list[dict]:
    period = get_period(session, period_id)
    if period.status != "CLOSED":
        raise ApiError(409, "PERIOD_NOT_CLOSED", f"Period {period_id} is not closed")
    rows = session.exec(select(Payout).where(Payout.period_id == period_id).order_by(Payout.seller_id)).all()
    return [
        {
            "seller_id": p.seller_id,
            "quota": money_str(p.quota_cents),
            "net_credited": money_str(p.credited_cents),
            "attainment_pct": p.attainment_pct,
            "qualified": p.qualified,
            "payout": money_str(p.payout_cents),
        }
        for p in rows
    ]
