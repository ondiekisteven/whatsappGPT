from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class UserBase(BaseModel):
    msisdn: str
    name: Optional[str]
    referral_code: str
    invited_by_id: Optional[int]


class User(UserBase):
    id: int


class PaymentBase(BaseModel):
    msisdn: str
    amount: int
    trx_id: str
    channel: str = 'MPESA'
    request_dump: str


class Payment(PaymentBase):
    id: int
    date_created: datetime


class NewPaymentSchema(BaseModel):
    TransactionAmount: int
    SenderMSISDN: str
    TransactionID: str

