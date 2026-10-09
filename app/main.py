from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from sqlmodel import Session, select

from . import VERSION, service
from .db import init_db, make_engine
from starlette.exceptions import HTTPException as StarletteHTTPException

from .errors import (ApiError, api_error_handler, http_error_handler, unhandled_error_handler,
                     validation_error_handler)
from .models import Credit, Period, Txn
from .schemas import ImportIn, QuotaIn, SellerIn, SellerOut, SellerPatch, TransactionIn, money_str


def create_app(database_url: str | None = None) -> FastAPI:
    engine = make_engine(database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(engine)
        yield

    app = FastAPI(title="Commission Engine", version=VERSION, lifespan=lifespan)
    app.state.engine = engine
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    def get_session():
        with Session(engine) as session:
            yield session

    def txn_out(txn: Txn, credits) -> dict:
        return {
            "transaction_id": txn.transaction_id,
            "type": txn.type,
            "txn_date": txn.txn_date.isoformat(),
            "store_id": txn.store_id,
            "amount": money_str(txn.amount_cents),
            "original_transaction_id": txn.original_transaction_id,
            "period_id": txn.period_id,
            "credits": [
                {"seller_id": c.seller_id, "split_pct": c.split_pct, "credit": money_str(c.credit_cents)}
                for c in credits
            ],
        }

    @app.get("/health")
    def health():
        return {"status": "ok", "version": VERSION}

    @app.post("/sellers", status_code=201, response_model=SellerOut)
    def create_seller(body: SellerIn, session: Session = Depends(get_session)):
        return service.create_seller(session, body)

    @app.get("/sellers/{seller_id}", response_model=SellerOut)
    def get_seller(seller_id: str, session: Session = Depends(get_session)):
        return service.get_seller(session, seller_id)

    @app.patch("/sellers/{seller_id}", response_model=SellerOut)
    def patch_seller(seller_id: str, body: SellerPatch, session: Session = Depends(get_session)):
        return service.update_seller(session, seller_id, body)

    @app.get("/periods")
    def list_periods(session: Session = Depends(get_session)):
        periods = session.exec(select(Period).order_by(Period.start_date)).all()
        return [
            {"period_id": p.period_id, "start_date": p.start_date.isoformat(),
             "end_date": p.end_date.isoformat(), "status": p.status}
            for p in periods
        ]

    @app.put("/periods/{period_id}/quotas/{seller_id}")
    def put_quota(period_id: str, seller_id: str, body: QuotaIn, response: Response,
                  session: Session = Depends(get_session)):
        quota, created = service.set_quota(session, period_id, seller_id, body.amount)
        response.status_code = 201 if created else 200
        return {"period_id": period_id, "seller_id": seller_id, "amount": money_str(quota.amount_cents)}

    @app.post("/transactions", status_code=201)
    def post_transaction(body: TransactionIn, session: Session = Depends(get_session)):
        txn, credits = service.create_transaction(session, body)
        return txn_out(txn, credits)

    @app.get("/transactions/{transaction_id}")
    def get_transaction(transaction_id: str, session: Session = Depends(get_session)):
        txn = session.get(Txn, transaction_id)
        if txn is None:
            raise ApiError(404, "TRANSACTION_NOT_FOUND", f"Transaction {transaction_id} does not exist")
        credits = session.exec(
            select(Credit).where(Credit.transaction_id == transaction_id).order_by(Credit.line_no)
        ).all()
        return txn_out(txn, credits)

    @app.post("/imports/transactions", status_code=201)
    def import_transactions(body: ImportIn, session: Session = Depends(get_session)):
        return service.import_transactions(session, body.transactions)

    @app.get("/periods/{period_id}/sellers/{seller_id}/statement")
    def get_statement(period_id: str, seller_id: str, session: Session = Depends(get_session)):
        return service.statement(session, period_id, seller_id)

    @app.post("/periods/{period_id}/close")
    def close(period_id: str, session: Session = Depends(get_session)):
        return service.close_period(session, period_id)

    @app.get("/periods/{period_id}/payouts")
    def payouts(period_id: str, session: Session = Depends(get_session)):
        return service.list_payouts(session, period_id)

    return app


app = create_app()
