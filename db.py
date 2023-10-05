from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, DateTime, Text, Boolean
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

messages = Table('messages', metadata,
                 Column('id', Integer, primary_key=True),
                 Column('session_id', String(50), index=True),
                 Column('msisdn', String(20)),
                 Column('role', String(200)),
                 Column('content', Text),
                 Column('date_created', DateTime(timezone=True), server_default=func.now()),
                 Column('client_id', String(20)),
                 Column('message_id', String(200), nullable=True, default=None),
                 Column('success', Boolean, default=True)
                 )

payments = Table('mpesa_payments', metadata,
                 Column('id', Integer, primary_key=True),
                 Column('msisdn', String(20)),
                 Column('amount', Integer),
                 Column('trx_id', String(100), unique=True),
                 Column('date_created', DateTime(timezone=True), server_default=func.now()),
                 Column('channel', String(100)),
                 Column('request_dump', Text)
                 )

users = Table('users', metadata,
              Column('id', Integer, primary_key=True),
              Column('msisdn', String(20), unique=True),
              Column('name', String(150)),
              Column('referral_code', String(20), unique=True),
              Column('invited_by_id', Integer),
              Column('date_created', DateTime(timezone=True), server_default=func.now()),
              )

stk_waiting = Table('stk_waiting', metadata,
                    Column('id', Integer, primary_key=True),
                    Column('msisdn', String(20), index=True),
                    Column('client_id', String(20)),
                    Column('amount', Integer),
                    Column('target', String(20)),
                    Column('fulfilled', Boolean, default=False),
                    Column('version', Integer, default=1)
                    )

openai_keys = Table('openai_keys', metadata,
                    Column('id', Integer, primary_key=True, autoincrement=True),
                    Column('key', String(150), index=True),
                    Column('comment', String(200), nullable=True),
                    Column('enabled', Boolean, default=True),
                    Column('date_created', DateTime(timezone=True), server_default=func.now()),
                    )

bot_adverts = Table('bot_adverts', metadata,
                    Column('id', Integer, primary_key=True, autoincrement=True),
                    Column('name', String(255), nullable=False, index=True, unique=True),
                    Column('text', Text),
                    Column('active', Boolean, default=False),
                    Column('date_created', DateTime(timezone=True), server_default=func.now()),
                    Column('date_updated', DateTime(timezone=True), server_onupdate=func.now()),
                    )


received_sms = Table('received_sms', metadata,
                     Column('id', Integer, primary_key=True, autoincrement=True),
                     Column('from', String(255), nullable=False),
                     Column('text', Text),
                     Column('sent_timestamp', String(255), nullable=False),
                     Column('received_timestamp', String(255), nullable=False),
                     Column('sim', String(150), nullable=True),
                     Column('version', Integer, default=2),
                     Column('date_created', DateTime(timezone=True), server_default=func.now()),
                     )
