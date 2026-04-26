from typing import Literal

from pydantic import BaseModel, Field


class PaymentCreateRequest(BaseModel):
    amount: int = Field(gt=0)
    payment_method: Literal["sbp", "card"]
    description: str | None = None


class PaymentCreateResponse(BaseModel):
    id: int
    platega_transaction_id: str
    status: str
    payment_url: str
    expires_in: str | None = None


class PaymentStatusResponse(BaseModel):
    id: int
    status: str
    balance: int
    amount: int
    payment_url: str | None = None
    expires_in: str | None = None
    is_completed: bool


class PaymentCallbackPayload(BaseModel):
    id: str
    amount: int
    currency: str
    status: str
    paymentMethod: int
