from pydantic import BaseModel, EmailStr


class EmailCodeRequest(BaseModel):
    email: EmailStr


class EmailLoginRequest(BaseModel):
    email: EmailStr
    code: str


class MessageResponse(BaseModel):
    message: str


class SessionUser(BaseModel):
    id: int
    email: EmailStr
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
    email: EmailStr
    balance: int
