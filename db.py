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
                 Column('client_id', String(20))
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
                    Column('fulfilled', Boolean, default=False)
                    )
