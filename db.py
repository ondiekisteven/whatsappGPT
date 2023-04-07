from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, DateTime, Text
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
                 )

users = Table('mpesa_payments', metadata,
              Column('id', Integer, primary_key=True),
              Column('msisdn', String(20)),
              Column('amount', Integer),
              Column('trx_id', String(100)),
              Column('date_created', DateTime(timezone=True), server_default=func.now()),
              )
