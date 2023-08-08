import datetime
import os
import random
import string

import phonenumbers
import requests
from phonenumbers import NumberParseException

import crud
from constants import r, NOT_PAID, DEPLETED, PAID, FREE_RESPONSES, BOT_NUMBERS, SIMULATED, EXPIRED, FREE_TRIAL, \
    EXPIRED_NOTIFIED, SUBSCRIPTION_EXPIRED_NOTIFIED, USERS, REFERRAL_CODES, REFERRAL_CODE_NOT_FOUND_MESSAGE, \
    USER_HAS_ANOTHER_INVITE_MESSAGE, USER_MORE_THAN_2_DAYS_MESSAGE, UPLINE_ADDED_MESSAGE, DOWNLINE_ADDED_MESSAGE, \
    logger, LESSON_SUBSCRIBED, LESSON_UNSUBSCRIBED, LESSON_ACTION_ERROR
from crud import save_messages
from schema import UserBase
from wp import send_message_base


def send_notification(client_id, msisdn, version, session_id=None, message=None):
    if not client_id or client_id is None:
        logger.warning("NO CLIENT ID FOUND. CAN NOT SEND NOTIFICATION")
        return
    if session_id is None:
        session_id = str(datetime.datetime.now().timestamp())
    new_msgs = [
        {'role': 'notification', 'content': message, 'msisdn': msisdn,
         'session_id': f'NOTIF-{session_id}', 'client_id': client_id}
    ]
    send_message_base(client_id, msisdn, message, version=version)
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

        handle_save_user(body)


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


def add_users(msisdn):
    # Adds user msisdn to list of users on redis
    return r.sadd(USERS, msisdn)


def expire_key_at_midnight(key):
    now = datetime.datetime.now()

    # set the key to expire at midnight
    expire_time = datetime.datetime(now.year, now.month, now.day, 23, 59, 59)
    r.expireat(key, when=int(expire_time.timestamp()))


def check_for_expiry(msisdn):
    last_payment = crud.get_last_payment(msisdn)

    if not last_payment:
        no_of_days_used = crud.get_number_of_days_used_not_paid(msisdn)
        expired = no_of_days_used >= FREE_TRIAL
        should_renew = False
        logger.info(f"No of days used -> {no_of_days_used} , expired -> {expired}")
    else:
        time_delta = datetime.datetime.now() - last_payment.date_created
        should_renew = time_delta.days >= 2
        expired = False
        logger.info(f"User has paid for the bot before. Should renew -> {should_renew}")

    return {
        'should_renew': should_renew,
        'expired': expired
    }


def add_depleted(msisdn):
    added = r.sadd(DEPLETED, msisdn)

    expire_key_at_midnight(DEPLETED)

    return added


def add_to_expired_and_notified(msisdn):
    added = r.sadd(EXPIRED_NOTIFIED, msisdn)

    expire_key_at_midnight(EXPIRED_NOTIFIED)

    return added


def add_to_subscription_expired_and_notified(msisdn):
    added = r.sadd(SUBSCRIPTION_EXPIRED_NOTIFIED, msisdn)

    expire_key_at_midnight(SUBSCRIPTION_EXPIRED_NOTIFIED)

    return added


def check_paid_status(msisdn: str):
    paid_expiry = r.hget(PAID, msisdn)

    if paid_expiry:
        paid_expiry = datetime.datetime.fromtimestamp(float(paid_expiry))
        if paid_expiry < datetime.datetime.now():

            # user payment has expired,
            # add to expired list,
            r.sadd(EXPIRED, msisdn)
            # remove from paid list
            r.hdel(PAID, msisdn)
            logger.warning("User subscription has expired")
            return -5
        else:
            # user has paid and payment has not expired
            return -1
    else:
        # check if they have used for more than <TRIAL_PERIOD_LENGTH> days
        trial_period_over = r.sismember(EXPIRED, msisdn)
        if trial_period_over:
            logger.warning("User trial has expired")
            return -2
        not_paid = r.hget(NOT_PAID, msisdn)
        if not_paid is not None:
            expire_key_at_midnight(NOT_PAID)
            # user is in not_paid list, we return remaining free responses
            return not_paid
        else:
            expiry_status = check_for_expiry(msisdn)
            if expiry_status['expired']:
                r.sadd(EXPIRED, msisdn)
                logger.warning("User trial has expired and is not in expired list")
                return -2

            if expiry_status['should_renew']:
                r.sadd(EXPIRED, msisdn)
                logger.warning("User subscription has expired but not found in expired list")
                return -5

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


def new_random_code():
    length = random.randint(4, 5)
    letters = string.ascii_uppercase + string.digits
    code = ''.join(random.choice(letters) for i in range(length))
    while r.sismember(REFERRAL_CODES, code):
        new_random_code()
    return f'REF-{code}'


def _get_name(sender: dict):
    if 'shortName' in sender:
        return sender['shortName']
    if 'pushname' in sender:
        return sender['pushname']
    if 'name' in sender:
        return sender['name']
    return None


def handle_save_user(data: dict):
    msisdn = data.get('from').split('@')[0]

    if r.sismember(USERS, msisdn):
        return
    logger.info(f'saving user: {data.get("sender")}')

    _gname = _get_name(data.get('sender'))
    name = _gname if _gname is not None else data.get('notifyName') if 'notifyName' in data.keys() else None
    referral_code = new_random_code()
    try:

        crud.save_user(UserBase(msisdn=msisdn, referral_code=referral_code, name=name))
    except Exception as x:
        logger.exception(x)
        return
    else:
        add_users(msisdn)
        r.sadd(REFERRAL_CODES, referral_code)

    if crud.get_number_of_days_used_not_paid(msisdn) > 1:
        if data.get('body').upper().startswith('REF'):
            logger.warning('Can Not Add Referer for old user')
        return

    if data.get('body').upper().startswith('REF'):
        upline = crud.get_user_by_referral_code(data.get('body').split(' ')[0])
        if upline:
            upline_id = upline.id
            crud.add_upline(msisdn, upline_id)


def handle_referral_msg(data: dict, version):
    referral_code = data.get('body').split(' ')[0]
    referer = crud.get_user_by_referral_code(referral_code)
    msisdn = data.get('from').split('@')[0]
    client_id = data.get('client_id')

    # if referral code is not associated with any user
    if not referer:
        send_notification(
            client_id=client_id, msisdn=msisdn, message=REFERRAL_CODE_NOT_FOUND_MESSAGE, version=version)
        logger.error(f'Referral Code Not Found. Code: {referral_code}, ')
        return

    user = crud.get_user_by_msisdn(msisdn)
    if user.invited_by_id:
        if user.invited_by_id == referer.id:
            logger.info("Referral code has already been processed. ")
            return
        # user already has a referer, we discard any subsequent requests
        logger.warning('User already has an invite. Cannot use referral code again')
        send_notification(
            client_id=client_id, msisdn=msisdn, message=USER_HAS_ANOTHER_INVITE_MESSAGE, version=version)
        return

    if crud.get_number_of_days_used_not_paid(msisdn) > 2:
        logger.info("User has used the bot more than 2 days. They cannot add an invite code to their account")
        send_notification(
            client_id=client_id, msisdn=msisdn, message=USER_MORE_THAN_2_DAYS_MESSAGE, version=version
        )
        return

    logger.info("Adding upline to use")
    logger.info(f'referer: {referer.__dict__}')
    logger.info(f'downline: {user.__dict__}')
    crud.add_upline(msisdn, referer.id)
    send_notification(client_id, msisdn, message=UPLINE_ADDED_MESSAGE.format(
        referer_msisdn=referer.msisdn,
        credits_count=FREE_RESPONSES,
        free_trial=FREE_TRIAL
    ), version=version)
    send_notification(client_id, referer.msisdn, message=DOWNLINE_ADDED_MESSAGE.format(
        downline_msisdn=msisdn,
        downlines_count=crud.get_downlines_count(referer.id)
    ), version=version)
    logger.info("Done processing user...")


def handle_getting_code(data: dict, version):
    msisdn = data.get('from').split("@")[0]
    code = crud.get_user_by_msisdn(msisdn)
    send_notification(data.get('client_id'), data.get('from'), message=f"""
    Your referral code is {code.referral_code}
    
    Copy the code and send it to users to invite them 
    
    *NOTE: ASK USERS TO SEND THE INVITE CODE AT LEAST TWICE. TELL USERS TO SEND THE MESSAGE TWICE TO THE BOT FOR THE CODE TO REFLECT CORRECTLY*
    """, version=version)
    send_notification(data.get('client_id'), data.get('from'), message=code.referral_code, version=version)


def request_subscription(payload):
    res = requests.post(os.getenv('LESSON_SUBSCRIPTION_API'), json=payload)
    logger.info(f"Subscribe Response -> {res.status_code} : {res.text}")
    return res.status_code in [200, 201]


def handle_lesson_subscription(msisdn, name, text, client_id, version):
    commands = [t for t in text.lower().split(" ") if t]
    payload = {
        "name": name,
        "msisdn": msisdn,
    }
    if commands[0] == '.join':
        # subscribing to the lesson
        payload['active'] = True

    elif commands[0] == '.stop':
        # unsubscribing
        payload['active'] = False

    else:
        # unknown command
        logger.info("Invalid Command Nothing to do")
        return

    if commands[1] == 'lesson':
        success = request_subscription(payload)
        if success:
            if payload['active']:
                send_notification(client_id, msisdn, version, message=LESSON_SUBSCRIBED.format(name=name))
            else:
                send_notification(client_id, msisdn, version, message=LESSON_UNSUBSCRIBED.format(name=name))

        else:
            send_notification(client_id, msisdn, version, message=LESSON_ACTION_ERROR)
