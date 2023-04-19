import datetime
import logging
import os

import phonenumbers
from phonenumbers import NumberParseException

from constants import r, NOT_PAID, DEPLETED, PAID, FREE_RESPONSES, BOT_NUMBERS, SIMULATED
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


def update_clients(body: dict):
    """
    Updates the list of bot clients, and the phone numbers they are operating on.
    For example, sets WA10001 -> 254712345678

    """
    if 'ack' in body and body['ack'] == 1:
        client_id = body.get('client_id')
        msisdn = body.get('to').replace('@c.us', '')

        r.hset(BOT_NUMBERS, msisdn, client_id)
        expire_key_at_midnight(BOT_NUMBERS)


def add_simulated_msg_id(msg_id):
    """
    Saves a list of messages that have been simulated, and processed. Since we send simulation messages to a group,
    the message may be picked more than once by clients, so once it has been processed by one client, it will be added
    here to prevent other clients from processing it
    """
    added = r.sadd(SIMULATED, msg_id)
    expire_key_at_midnight(DEPLETED)

    return added


def decrement_response_count(msisdn: str):
    if not r.hexists(PAID, msisdn):
        # decrement remaining credits only if user has not paid
        r.hincrby(NOT_PAID, msisdn, -1)


def add_paid(msisdn, expiry: datetime):
    r.hset(PAID, msisdn, str(expiry.timestamp()))


def expire_key_at_midnight(key):
    now = datetime.datetime.now()

    # set the key to expire at midnight
    expire_time = datetime.datetime(now.year, now.month, now.day, 23, 59, 59)
    r.expireat(key, when=int(expire_time.timestamp()))


def add_depleted(msisdn):
    added = r.sadd(DEPLETED, msisdn)

    expire_key_at_midnight(DEPLETED)

    return added


def check_paid_status(msisdn: str):
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
        not_paid = r.hget(NOT_PAID, msisdn)
        if not_paid is not None:
            expire_key_at_midnight(NOT_PAID)
            # user is in not_paid list, we return remaining free responses
            return not_paid
        else:
            # user was not found on paid and unpaid list. add to unpaid for now
            r.hset(NOT_PAID, msisdn, FREE_RESPONSES)
            return FREE_RESPONSES


def parse_msisdn(msisdn: str, log=True):
    try:
        if len(msisdn) == 9 or len(msisdn) == 10:
            phone = phonenumbers.parse(msisdn, 'KE')
        elif msisdn.startswith('+'):
            phone = phonenumbers.parse(msisdn, None)
        else:
            phone = phonenumbers.parse(f'+{msisdn}', None)
    except NumberParseException as x:
        if log:
            logger.exception(x)
        return

    return phonenumbers.format_number(phone, phonenumbers.PhoneNumberFormat.E164).replace('+', '')
