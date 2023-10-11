import random

from sqlalchemy import select, text

from constants import engine, logger
from db import users, payments, messages, stk_waiting, openai_keys, bot_adverts, received_sms, sms_index, \
    malawi_payments_waiting, malawi_payments
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


def save_malawi_payment(payment: PaymentBase):
    db = get_db()
    try:
        db.execute(malawi_payments.insert(), payment.dict())
        db.commit()
    except Exception as x:
        logger.exception(x)
        db.rollback()
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


def save_stk_waiting(msisdn, client_id, amount, target, version=2):
    db = get_db()
    try:
        db.execute(stk_waiting.insert(), {
            'msisdn': msisdn,
            'client_id': client_id,
            'amount': amount,
            'target': target,
            'version': version
        })
    except Exception as x:
        logger.exception(x)
        db.rollback()
    else:
        db.commit()
    finally:
        db.close()


def save_malawi_waiting(msisdn, client_id, amount, target, version=2):
    db = get_db()
    try:
        db.execute(malawi_payments_waiting.insert(), {
            'msisdn': msisdn,
            'client_id': client_id,
            'amount': amount,
            'target': target,
            'version': version
        })
    except Exception as x:
        logger.exception(x)
        db.rollback()
    else:
        db.commit()
    finally:
        db.close()


def get_malawi_waiting(msisdn, amount):
    db = get_db()
    stmt = select(stk_waiting) \
        .where(malawi_payments_waiting.c.msisdn == msisdn) \
        .where(stk_waiting.c.fulfilled == False) \
        .order_by(stk_waiting.c.id.desc())
    result = db.execute(stmt)
    stk = result.first()
    db.close()
    return stk


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


def mark_stk_waiting_fulfilled(waiting_id, table=stk_waiting):
    db = get_db()
    try:
        db.execute(table.update().where(stk_waiting.c.id == waiting_id).values(fulfilled=True))
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


def get_paid_for_key():
    db = get_db()
    stmt = select(openai_keys) \
        .where(openai_keys.c.enabled == True)
    result = db.execute(stmt).fetchall()
    db.close()

    key = random.choice(result)
    return key


def save_new_advert(advert_name, advert_text, version=2):
    db = get_db()
    try:
        db.execute(bot_adverts.insert(), {
            'name': advert_name,
            'advert_text': advert_text,
        })
    except Exception as x:
        logger.exception(x)
        db.rollback()
    else:
        db.commit()
    finally:
        db.close()


def save_new_received_sms(from_, sms_text, sent_timestamp, received_timestamp, sim, version=2):
    db = get_db()
    response = True
    try:
        db.execute(received_sms.insert(), {
            'from': from_,
            'text': sms_text,
            'sent_timestamp': sent_timestamp,
            'received_timestamp': received_timestamp,
            'sim': sim,
            'version': version
        })

        db.commit()

    except Exception as x:
        logger.exception(x)
        db.rollback()
        response = False
    finally:
        db.close()
    return response


def save_index_sms(from_, sms_text, sent_timestamp, received_timestamp, sim, version=2):
    db = get_db()
    try:
        db.execute(sms_index.insert(), {
            'from': from_,
            'text': sms_text,
            'sent_timestamp': sent_timestamp,
            'received_timestamp': received_timestamp,
            'sim': sim,
            'version': version
        })
    except Exception as x:
        logger.exception(x)
        db.rollback()
    else:
        db.commit()
    finally:
        db.close()


def get_active_adverts():
    db = get_db()
    stmt = select(bot_adverts).where(bot_adverts.c.active == True) \
        .order_by(bot_adverts.c.id)
    result = db.execute(stmt)
    data = result.fetchall()

    db.close()
    return data
