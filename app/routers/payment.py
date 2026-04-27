import json

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.crud.spa import add_transaction
from app.database import get_db
from app.dependencies import get_current_user
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.transaction import (
    PaymentCallbackPayload,
    PaymentCreateRequest,
    PaymentCreateResponse,
    PaymentStatusResponse,
)
from app.services.platega import (
    PlategaConfigurationError,
    PlategaError,
    platega_service,
)

router = APIRouter(prefix="/api/payments", tags=["payments"])
settings = get_settings()

PLATEGA_METHODS = {
    "sbp": 2,
    "card": 11,
    "crypto": 13,
}
PLATEGA_SUCCESS_STATUSES = {"CONFIRMED"}
PLATEGA_REVERT_STATUSES = {"CHARGEBACKED"}


def _build_return_url(status_name: str) -> str:
    base = settings.BACKEND_URL.rstrip("/")
    return f"{base}/api/payments/redirect/{status_name}"


async def _get_user_transaction(db: AsyncSession, user: User, transaction_id: int) -> Transaction:
    result = await db.execute(
        select(Transaction).where(
            Transaction.id == transaction_id,
            Transaction.user_id == user.id,
        )
    )
    transaction = result.scalar_one_or_none()
    if transaction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return transaction


async def _apply_platega_status(
    db: AsyncSession,
    transaction: Transaction,
    new_status: str,
) -> None:
    previous_status = transaction.platega_status
    normalized_status = new_status.upper()
    transaction.platega_status = normalized_status

    if normalized_status in PLATEGA_SUCCESS_STATUSES and previous_status not in PLATEGA_SUCCESS_STATUSES:
        user = await db.get(User, transaction.user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        user.balance += transaction.amount
    elif normalized_status in PLATEGA_REVERT_STATUSES and previous_status in PLATEGA_SUCCESS_STATUSES:
        user = await db.get(User, transaction.user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        user.balance -= transaction.amount
        await add_transaction(db, user, "refund", -transaction.amount, "Chargeback Platega")


@router.post("/create", response_model=PaymentCreateResponse)
async def create_payment(
    payload: PaymentCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.amount <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Amount must be positive")

    payment_method = PLATEGA_METHODS.get(payload.payment_method)
    if payment_method is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported payment method")

    description = payload.description or f"Пополнение баланса на {payload.amount} RUB"

    transaction = Transaction(
        user_id=current_user.id,
        type="topup",
        amount=payload.amount,
        description=description,
        platega_status="PENDING",
    )
    db.add(transaction)
    await db.flush()

    callback_payload = json.dumps(
        {
            "user_id": current_user.id,
            "local_transaction_id": transaction.id,
            "payment_method": payload.payment_method,
        },
        ensure_ascii=True,
    )

    try:
        platega_response = await platega_service.create_payment(
            amount=payload.amount,
            currency="RUB",
            description=description,
            return_url=_build_return_url("success"),
            failed_url=_build_return_url("failed"),
            payload=callback_payload,
            payment_method=payment_method,
        )
    except PlategaConfigurationError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except PlategaError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Platega error: {exc}") from exc

    transaction.platega_transaction_id = platega_response["transactionId"]
    transaction.platega_status = platega_response.get("status", "PENDING")
    transaction.platega_url = platega_response.get("redirect")
    transaction.platega_expires_in = platega_response.get("expiresIn")
    transaction.platega_rate = platega_response.get("usdtRate")
    transaction.platega_payload = callback_payload

    await db.commit()
    await db.refresh(transaction)

    return PaymentCreateResponse(
        id=transaction.id,
        platega_transaction_id=transaction.platega_transaction_id,
        status=transaction.platega_status or "PENDING",
        payment_url=transaction.platega_url or "",
        expires_in=transaction.platega_expires_in,
    )


@router.get("/{transaction_id}/status", response_model=PaymentStatusResponse)
async def get_payment_status(
    transaction_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    transaction = await _get_user_transaction(db, current_user, transaction_id)
    if not transaction.platega_transaction_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Platega transaction is not linked")

    try:
        platega_status = await platega_service.get_transaction(transaction.platega_transaction_id)
    except PlategaConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except PlategaError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Platega error: {exc}") from exc

    transaction.platega_expires_in = platega_status.get("expiresIn") or transaction.platega_expires_in
    transaction.platega_url = platega_status.get("redirect") or transaction.platega_url
    await _apply_platega_status(db, transaction, platega_status.get("status", transaction.platega_status or "PENDING"))

    await db.commit()
    await db.refresh(current_user)
    await db.refresh(transaction)

    return PaymentStatusResponse(
        id=transaction.id,
        status=transaction.platega_status or "PENDING",
        balance=current_user.balance,
        amount=transaction.amount,
        payment_url=transaction.platega_url,
        expires_in=transaction.platega_expires_in,
        is_completed=(transaction.platega_status or "").upper() in {"CONFIRMED", "CANCELED", "CHARGEBACKED"},
    )


@router.post("/platega/callback", status_code=status.HTTP_200_OK)
async def platega_callback(
    payload: PaymentCallbackPayload,
    db: AsyncSession = Depends(get_db),
    x_merchant_id: str | None = Header(None, alias="X-MerchantId"),
    x_secret: str | None = Header(None, alias="X-Secret"),
):
    expected_merchant_id = settings.PLATEGA_MERCHANT_ID.strip()
    expected_secret = settings.PLATEGA_SECRET.strip()
    if x_merchant_id != expected_merchant_id or x_secret != expected_secret:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid callback credentials")

    result = await db.execute(
        select(Transaction).where(Transaction.platega_transaction_id == payload.id)
    )
    transaction = result.scalar_one_or_none()
    if transaction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    await _apply_platega_status(db, transaction, payload.status)
    await db.commit()
    return Response(status_code=status.HTTP_200_OK)


@router.get("/redirect/success")
async def payment_success_redirect():
    return {"message": "Payment flow completed. Return to the app and refresh the payment status."}


@router.get("/redirect/failed")
async def payment_failed_redirect():
    return {"message": "Payment was canceled or failed. Return to the app and try again."}
