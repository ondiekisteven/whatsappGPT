from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine, MetaData
from sqlalchemy.pool import QueuePool
from sqlalchemy.sql.functions import func


def create_db(cfg: dict):
    return create_engine(
        f'mysql+pymysql://{cfg["username"]}:{cfg["password"]}@{cfg["host"]}:{cfg["port"]}/{cfg["database"]}',
        pool_recycle=cfg.get('pool_recycle', 3600),  # how long before connections are recycled
        pool_size=cfg.get('pool_size', 20),  # number of connections in pool
        echo_pool='debug' if int(cfg['debug']) == 1 else False,
        poolclass=QueuePool,
        pool_use_lifo=True
    )


metadata = MetaData()

db = SQLAlchemy()


class Message(db.Model):
    __tablename__ = 'messages'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(50), index=True)
    msisdn = db.Column(db.String(20))
    role = db.Column(db.String(200))
    content = db.Column(db.Text)
    date_created = db.Column(db.DateTime(timezone=True), server_default=func.now())
    client_id = db.Column(db.String(20))
    message_id = db.Column(db.String(200), nullable=True, default=None)
    success = db.Column(db.Boolean, default=True)


class MpesaPayment(db.Model):
    __tablename__ = 'mpesa_payments'

    id = db.Column(db.Integer, primary_key=True)
    msisdn = db.Column(db.String(20))
    amount = db.Column(db.Integer)
    trx_id = db.Column(db.String(100), unique=True)
    date_created = db.Column(db.DateTime(timezone=True), server_default=func.now())
    channel = db.Column(db.String(100))
    request_dump = db.Column(db.Text)


class MalawiPayment(db.Model):
    __tablename__ = 'malawi_payments'

    id = db.Column(db.Integer, primary_key=True)
    msisdn = db.Column(db.String(20))
    amount = db.Column(db.Integer)
    trx_id = db.Column(db.String(100), unique=True)
    date_created = db.Column(db.DateTime(timezone=True), server_default=func.now())
    channel = db.Column(db.String(100))
    request_dump = db.Column(db.Text)


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    msisdn = db.Column(db.String(20), unique=True)
    name = db.Column(db.String(150))
    referral_code = db.Column(db.String(20), unique=True)
    invited_by_id = db.Column(db.Integer)
    date_created = db.Column(db.DateTime(timezone=True), server_default=func.now())


class StkWaiting(db.Model):
    __tablename__ = 'stk_waiting'

    id = db.Column(db.Integer, primary_key=True)
    msisdn = db.Column(db.String(20), index=True)
    client_id = db.Column(db.String(20))
    amount = db.Column(db.Integer)
    target = db.Column(db.String(20))
    fulfilled = db.Column(db.Boolean, default=False)
    version = db.Column(db.Integer, default=1)


class MalawiPaymentsWaiting(db.Model):
    __tablename__ = 'malawi_payments_waiting'

    id = db.Column(db.Integer, primary_key=True)
    msisdn = db.Column(db.String(20), index=True)
    client_id = db.Column(db.String(20))
    amount = db.Column(db.Integer)
    target = db.Column(db.String(20))
    fulfilled = db.Column(db.Boolean, default=False)
    version = db.Column(db.Integer, default=1)


class MalawiFlutterPaymentsWaiting(db.Model):
    __tablename__ = 'malawi_flutter_payments_waiting'

    id = db.Column(db.Integer, primary_key=True)
    msisdn = db.Column(db.String(20), index=True)
    client_id = db.Column(db.String(20))
    amount = db.Column(db.Integer)
    target = db.Column(db.String(20))
    fulfilled = db.Column(db.Boolean, default=False)
    payment_url = db.Column(db.Text)
    network = db.Column(db.String(50))
    trx_ref = db.Column(db.String(50))
    version = db.Column(db.Integer, default=1)


class MalawiFlutterPayments(db.Model):
    __tablename__ = 'malawi_flutter_payments'

    id = db.Column(db.Integer, primary_key=True)
    msisdn = db.Column(db.String(20), index=True)
    client_id = db.Column(db.String(20))
    amount = db.Column(db.Integer)
    target = db.Column(db.String(20))
    trx_id = db.Column(db.String(50))
    event_type = db.Column(db.String(50))
    status = db.Column(db.String(200))
    flw_ref = db.Column(db.String(200))
    version = db.Column(db.Integer, default=1)


class TanzaniaPaymentsWaiting(db.Model):
    __tablename__ = 'tanzania_flutter_payments_waiting'

    id = db.Column(db.Integer, primary_key=True)
    msisdn = db.Column(db.String(20), index=True)
    client_id = db.Column(db.String(20))
    amount = db.Column(db.Integer)
    network = db.Column(db.String(100))
    target = db.Column(db.String(20))
    fulfilled = db.Column(db.Boolean, default=True)
    trx_ref = db.Column(db.String(200))
    email = db.Column(db.String(200))
    full_name = db.Column(db.String(200))
    version = db.Column(db.Integer, default=1)


class OpenAIKey(db.Model):
    __tablename__ = 'openai_keys'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    key = db.Column(db.String(150), index=True)
    comment = db.Column(db.String(200), nullable=True)
    enabled = db.Column(db.Boolean, default=True)
    date_created = db.Column(db.DateTime(timezone=True), server_default=func.now())


class BotAdvert(db.Model):
    __tablename__ = 'bot_adverts'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False, index=True, unique=True)
    Text = db.Column(db.Text)
    active = db.Column(db.Boolean, default=False)
    date_created = db.Column(db.DateTime(timezone=True), server_default=func.now())
    date_updated = db.Column(db.DateTime(timezone=True), server_onupdate=func.now())


class ReceivedSMS(db.Model):
    __tablename__ = 'received_sms'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    from_ = db.Column(db.String(255), nullable=False, name='from')
    text = db.Column(db.Text)
    sent_timestamp = db.Column(db.String(255), nullable=False)
    received_timestamp = db.Column(db.String(255), nullable=False)
    sim = db.Column(db.String(150), nullable=True)
    version = db.Column(db.Integer, default=2)
    date_created = db.Column(db.DateTime(timezone=True), server_default=func.now())


class SMSIndex(db.Model):
    __tablename__ = 'sms_index'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    from_ = db.Column(db.String(255), nullable=False, name='from')
    text = db.Column(db.Text)
    sent_timestamp = db.Column(db.String(255), nullable=False)
    received_timestamp = db.Column(db.String(255), nullable=False)
    sim = db.Column(db.String(150), nullable=True)
    version = db.Column(db.Integer, default=2)
    date_created = db.Column(db.DateTime(timezone=True), server_default=func.now())
