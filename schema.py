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


class FlutterwavePayment(PaymentBase):
    client_id: str
    target: str
    event_type: str
    status: str
    flw_ref: str
    version: int


class Payment(PaymentBase):
    id: int
    date_created: datetime


class NewPaymentSchema(BaseModel):
    TransactionAmount: int
    SenderMSISDN: str
    TransactionID: str

