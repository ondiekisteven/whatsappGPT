import random

from sqlalchemy import select, text

from constants import engine, logger
from db import User, MpesaPayment, MalawiPayment, MalawiPaymentsWaiting, Message, OpenAIKey, StkWaiting, BotAdvert, \
    ReceivedSMS, SMSIndex, Music, TanzaniaPaymentsWaiting, MalawiFlutterPaymentsWaiting, MalawiFlutterPayments
from schema import UserBase, PaymentBase, FlutterwavePayment


def get_db():
    return engine.connect()


def save_user(user: UserBase):
    db = get_db()
    try:
        db.execute(User.__table__.insert(), user.dict())
        db.commit()
    except Exception as x:
        logger.exception(x)
        db.rollback()
    else:
        pass
    finally:
        db.close()


def get_user_by_referral_code(code: str):
    db = get_db()
    try:
        stmt = select(User).where(User.referral_code == code)
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
        stmt = select(User).where(User.msisdn == msisdn)
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
        stmt = select(User).where(User.id == user_id)
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
        db.execute(MpesaPayment.__table__.insert(), payment.dict())
        db.commit()
    except Exception as x:
        logger.exception(x)
        db.rollback()
        raise
    else:
        pass
    finally:
        db.close()


def save_malawi_payment(payment: PaymentBase):
    db = get_db()
    try:
        db.execute(MalawiPayment.__table__.insert(), payment.dict())
        db.commit()
    except Exception as x:
        logger.exception(x)
        db.rollback()
    finally:
        db.close()


def save_flutter_malawi_payment(payment: FlutterwavePayment):
    db = get_db()
    try:
        db.execute(MalawiFlutterPayments.__table__.insert(), payment.dict())
        db.commit()
    except Exception as x:
        logger.exception(x)
        db.rollback()
    finally:
        db.close()


def get_last_payment(msisdn):
    db = get_db()
    stmt = select(MpesaPayment).where(MpesaPayment.msisdn == msisdn).order_by(MpesaPayment.date_created.desc()).limit(1)
    result = db.execute(stmt).fetchone()
    db.close()
    return result


def get_messages(session_id):
    db = get_db()
    stmt = select(Message).where(Message.session_id == session_id)
    result = db.execute(stmt).fetchall()
    db.close()
    return result


def get_payments():
    db = get_db()
    stmt = select(MpesaPayment).order_by('date_created')
    result = db.execute(stmt).fetchall()
    db.close()
    return result


def save_messages(msg_objs: list):
    logger.info(f"saving : {msg_objs}")
    db = get_db()
    try:
        db.execute(Message.__table__.insert(), msg_objs)
        db.commit()
    except Exception as x:
        logger.exception(x)
        db.rollback()

    else:
        pass
    finally:
        db.close()


def save_stk_waiting(msisdn, client_id, amount, target, version=2):
    db = get_db()
    try:
        db.execute(StkWaiting.__table__.insert(), {
            'msisdn': msisdn,
            'client_id': client_id,
            'amount': amount,
            'target': target,
            'version': version
        })
        db.commit()
    except Exception as x:
        logger.exception(x)
        db.rollback()
    else:
        pass
    finally:
        db.close()


def save_malawi_waiting(msisdn, client_id, amount, target, version=2):
    db = get_db()
    try:
        db.execute(MalawiPaymentsWaiting.__table__.insert(), {
            'msisdn': msisdn,
            'client_id': client_id,
            'amount': amount,
            'target': target,
            'version': version
        })
        db.commit()
    except Exception as x:
        logger.exception(x)
        db.rollback()
    else:
        pass
    finally:
        db.close()


def get_malawi_waiting(msisdn, amount):
    db = get_db()
    stmt = select(MalawiPaymentsWaiting) \
        .where(MalawiPaymentsWaiting.msisdn == msisdn) \
        .where(MalawiPaymentsWaiting.fulfilled == False) \
        .order_by(MalawiPaymentsWaiting.id.desc())
    result = db.execute(stmt)
    stk = result.first()
    db.close()
    return stk


def get_malawi_flutter_waiting(msisdn, amount):
    db = get_db()
    stmt = select(MalawiPaymentsWaiting) \
        .where(MalawiFlutterPaymentsWaiting.msisdn == msisdn) \
        .where(MalawiFlutterPaymentsWaiting.fulfilled == False) \
        .order_by(MalawiFlutterPaymentsWaiting.id.desc())
    result = db.execute(stmt)
    stk = result.first()
    db.close()
    return stk


def get_stk_waiting(msisdn, amount):
    db = get_db()
    stmt = select(StkWaiting).where(StkWaiting.msisdn == msisdn).where(StkWaiting.fulfilled == False) \
        .order_by(StkWaiting.id)
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


def mark_stk_waiting_fulfilled(waiting_id, table):
    db = get_db()
    try:
        db.execute(table.__table__.update().where(table.id == waiting_id).values(fulfilled=True))
        db.commit()
    except Exception as x:
        logger.exception(x)
        db.rollback()
        raise
    else:
        pass
    finally:
        db.close()


def add_upline(msisdn, upline_id):
    db = get_db()
    try:
        db.execute(User.__table__.update().where(User.msisdn == msisdn).values(invited_by_id=upline_id))
        db.commit()
    except Exception as x:
        logger.exception(x)
        db.rollback()
        raise
    else:
        pass
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
    stmt = select(OpenAIKey) \
        .where(OpenAIKey.enabled == True)
    result = db.execute(stmt).fetchall()
    db.close()

    key = random.choice(result)
    return key


def save_new_advert(advert_name, advert_text, version=2):
    db = get_db()
    try:
        db.execute(BotAdvert.__table__.insert(), {
            'name': advert_name,
            'advert_text': advert_text,
        })
        db.commit()
    except Exception as x:
        logger.exception(x)
        db.rollback()
    else:
        pass
    finally:
        db.close()


def save_new_received_sms(from_, sms_text, sent_timestamp, received_timestamp, sim, version=2):
    db = get_db()
    response = True
    try:
        db.execute(ReceivedSMS.__table__.insert(), {
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
        db.execute(SMSIndex.__table__.insert(), {
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
    else:
        pass
    finally:
        db.close()


def get_active_adverts():
    db = get_db()
    stmt = select(BotAdvert).where(BotAdvert.active == True) \
        .order_by(BotAdvert.id)
    result = db.execute(stmt)
    data = result.fetchall()

    db.close()
    return data
