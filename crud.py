import logging

from sqlalchemy import Connection, select

from constants import engine
from db import users, payments, messages, stk_waiting
from schema import UserBase, PaymentBase

logger = logging.getLogger(__name__)


def get_db():
    return engine.connect()


def save_user(user: UserBase):
    db = get_db()
    try:
        db.execute(users.insert(), user.dict())
    except Exception as x:
        logger.exception(x)
        db.rollback()
    else:
        db.commit()
    finally:
        db.close()


def save_payment(payment: PaymentBase):
    db = get_db()
    try:
        db.execute(payments.insert(), payment.dict())
    except Exception as x:
        logger.exception(x)
        db.rollback()
        raise
    else:
        db.commit()
    finally:
        db.close()


def get_messages(session_id):
    db = get_db()
    stmt = select(messages).where(messages.c.session_id == session_id)
    result = db.execute(stmt).fetchall()
    db.close()
    return result


def save_messages(msg_objs: list):
    logger.info(f"saving : {msg_objs}")
    db = get_db()
    try:
        db.execute(messages.insert(), msg_objs)
    except Exception as x:
        logger.exception(x)
        db.rollback()

    else:
        db.commit()
    finally:
        db.close()


def save_stk_waiting(msisdn, client_id, amount, target):
    db = get_db()
    try:
        db.execute(stk_waiting.insert(), {'msisdn': msisdn, 'client_id': client_id, 'amount': amount, 'target': target})
    except Exception as x:
        logger.exception(x)
        db.rollback()
    else:
        db.commit()
    finally:
        db.close()


def get_stk_waiting(msisdn, amount):
    db = get_db()
    stmt = select(stk_waiting).where(stk_waiting.c.msisdn == msisdn).where(stk_waiting.c.fulfilled == False)\
        .order_by(stk_waiting.c.id)
    result = db.execute(stmt)
    if result.rowcount == 1:
        stk = result.fetchone()
    else:
        results = result.fetchall()
        stk = [item for item in results if item.amount == amount][-1]

    db.close()
    return stk


def mark_stk_waiting_fulfilled(waiting_id):
    db = get_db()
    try:
        db.execute(stk_waiting.update().where(stk_waiting.c.id == waiting_id).values(fulfilled=True))
    except Exception as x:
        logger.exception(x)
        db.rollback()
        raise
    else:
        db.commit()
    finally:
        db.close()
