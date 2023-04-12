import datetime
import logging
import os

from constants import r, NOT_PAID, DEPLETED, PAID, FREE_RESPONSES
from crud import save_messages
from wp import send_message_base

logger = logging.getLogger(__name__)


def send_notification(client_id, msisdn, session_id, message):
    new_msgs = [
        {'role': 'notification', 'content': message, 'msisdn': msisdn,
         'session_id': f'NOTIF-{session_id}', 'client_id': client_id}
    ]
    send_message_base(client_id, msisdn, message)
    save_messages(new_msgs)


def get_session_id(client_id, msisdn):
    rk = f'{client_id}:{msisdn}'
    sn_id = r.get(rk)
    if not sn_id:
        logger.info(f'{rk} has no active session id, creating one...')
        sn_id = str(datetime.datetime.now().timestamp())
        r.set(rk, sn_id)

    r.expire(rk, time=datetime.timedelta(minutes=int(os.getenv('SESSION_LENGTH_SECONDS', '10'))))
    return sn_id


def decrement_response_count(msisdn: str):
    r.hincrby(NOT_PAID, msisdn, -1)


def add_paid(msisdn, expiry: datetime):
    r.hset(PAID, msisdn, str(expiry.timestamp()))


def add_depleted(msisdn):
    added = r.sadd(DEPLETED, msisdn)

    now = datetime.datetime.now()

    # set the key to expire at midnight
    expire_time = datetime.datetime(now.year, now.month, now.day, 23, 59, 59)
    r.expireat(DEPLETED, when=int(expire_time.timestamp()))

    return added


def check_paid_status(msisdn: str):
    not_paid = r.hget(NOT_PAID, msisdn)
    if not_paid is not None:
        # user is in not_paid list, we return remaining free responses
        return not_paid
    else:
        paid_expiry = r.hget(PAID, msisdn)

        if paid_expiry:
            paid_expiry = datetime.datetime.fromtimestamp(float(paid_expiry))
            if paid_expiry < datetime.datetime.now():

                # user payment has expired,
                # add to unpaid list,
                r.hset(NOT_PAID, msisdn, FREE_RESPONSES)
                # remove from paid list
                r.hdel(PAID, msisdn)
                return FREE_RESPONSES
            else:
                # user has paid and payment has not expired
                return -1
        else:
            # user was not found on paid and unpaid list. add to unpaid for now
            r.hset(NOT_PAID, msisdn, FREE_RESPONSES)
            return FREE_RESPONSES
