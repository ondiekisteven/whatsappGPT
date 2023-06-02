from sqlalchemy import select, text

from constants import engine, logger
from db import users, payments, messages, stk_waiting
from schema import UserBase, PaymentBase


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


def get_user_by_referral_code(code: str):
    db = get_db()
    try:
        stmt = select(users).where(users.c.referral_code == code)
        result = db.execute(stmt).fetchone()
        db.close()
    except Exception as e:
        logger.exception(e)
        raise
    finally:
        db.close()
    return result


def get_user_by_msisdn(msisdn: str):
    db = get_db()
    try:
        stmt = select(users).where(users.c.msisdn == msisdn)
        result = db.execute(stmt).fetchone()
        db.close()
    except Exception as e:
        logger.exception(e)
        raise
    finally:
        db.close()
    return result


def get_downlines_count(user_id: int):
    db = get_db()
    try:
        stmt = text('select count(*) as count from users where invited_by_id=:user_id')
        result = db.execute(stmt, {'user_id': user_id}).fetchone()
    except Exception as x:
        logger.exception(x)
        count = 0
    else:
        count = result.count
    finally:
        db.close()
    return count


def get_user_by_id(user_id: int):
    db = get_db()
    try:
        stmt = select(users).where(users.c.id == user_id)
        result = db.execute(stmt).fetchone()
        db.close()
    except Exception as e:
        logger.exception(e)
        raise
    finally:
        db.close()
    return result


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


def get_last_payment(msisdn):
    db = get_db()
    stmt = select(payments).where(payments.c.msisdn == msisdn).order_by(payments.c.date_created.desc()).limit(1)
    result = db.execute(stmt).fetchone()
    db.close()
    return result


def get_messages(session_id):
    db = get_db()
    stmt = select(messages).where(messages.c.session_id == session_id)
    result = db.execute(stmt).fetchall()
    db.close()
    return result


def get_payments():
    db = get_db()
    stmt = select(payments).order_by('date_created')
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
    stmt = select(stk_waiting).where(stk_waiting.c.msisdn == msisdn).where(stk_waiting.c.fulfilled == False) \
        .order_by(stk_waiting.c.id)
    result = db.execute(stmt)
    if result.rowcount == 1:
        stk = result.fetchone()
    else:
        results = result.fetchall()
        stk = [item for item in results if item.amount == amount]
        if stk:
            return stk[-1]
        else:
            return None

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


def add_upline(msisdn, upline_id):
    db = get_db()
    try:
        db.execute(users.update().where(users.c.msisdn == msisdn).values(invited_by_id=upline_id))
    except Exception as x:
        logger.exception(x)
        db.rollback()
        raise
    else:
        db.commit()
    finally:
        db.close()


def get_number_of_days_used_not_paid(msisdn):
    db = get_db()
    # stmt = select(func.count(func.distinct(func.DATE(messages.c.date_created)).label('days'))) \
    #     .select_from(messages).where(messages.c.msisdn == msisdn).group_by()
    try:
        stmt = text('SELECT count(DISTINCT Date(date_created)) as total_days from messages where msisdn = :msisdn;')
        result = db.execute(stmt, {'msisdn': msisdn}).fetchone()
        total_days = result.total_days if result else None
    except Exception as x:
        logger.exception(x)
        return -1
    else:
        return total_days
    finally:
        db.close()
