from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class UserBase(BaseModel):
    msisdn: str
    name: Optional[str]
    free: bool = True
    last_free_notify: Optional[datetime]


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

