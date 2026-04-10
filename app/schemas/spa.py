from pydantic import BaseModel, EmailStr, Field


class EmailCodeRequest(BaseModel):
    email: EmailStr


class EmailLoginRequest(BaseModel):
    email: EmailStr
    code: str


class EmailPasswordRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)


class TelegramLoginRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class MessageResponse(BaseModel):
    message: str


class SessionUser(BaseModel):
    id: int
    email: str
    balance: int


class SessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: SessionUser


class DeviceCreateRequest(BaseModel):
    name: str
    type: str


class DeviceUpdateRequest(BaseModel):
    name: str


class DeviceResponse(BaseModel):
    id: str
    name: str
    type: str
    status: str
    expiryDate: str
    key: str


class TransactionResponse(BaseModel):
    id: str
    type: str
    amount: int
    date: str
    description: str


class TopUpRequest(BaseModel):
    amount: int


class TopUpResponse(BaseModel):
    newBalance: int


class ProfileResponse(BaseModel):
    email: str
    balance: int
    telegram_id: int | None = None
    telegram_username: str | None = None


class LinkTokenResponse(BaseModel):
    token: str
    bot_username: str
    deep_link: str
    expires_in: int


class LinkStatusResponse(BaseModel):
    linked: bool
    telegram_username: str | None = None


class ConfirmLinkRequest(BaseModel):
    token: str
    telegram_id: int
    telegram_username: str | None = None
    telegram_first_name: str | None = None


class ConfirmLinkResponse(BaseModel):
    success: bool = True
    user_email: str | None = None
    error: str | None = None
