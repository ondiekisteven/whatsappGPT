import datetime
import os
import random
import re
from typing import List, Dict

import cfg_load
import openai

from constants import DEPLETED_CREDITS_MESSAGE, engine, r, config_path, high, BOT_NUMBERS, \
    TRIAL_PERIOD_OVER, RENEW_SUBSCRIPTION_MESSAGE, logger, ERROR_GENERATING_RESPONSE, default, SECONDS_BEFORE_ADVERT, \
    adverts_queue
from crud import get_messages, save_messages, get_paid_for_key, get_last_payment
from db import metadata
from helpers import check_paid_status, add_depleted, get_session_id, decrement_response_count, \
    add_to_expired_and_notified, send_notification, add_to_subscription_expired_and_notified, send_advert, \
    get_upgrade_amount
from wp import send_message_base

metadata.create_all(engine)


def get_history(client_id, msisdn):
    session_id = get_session_id(client_id, msisdn)
    history = get_messages(session_id)
    system_msg = [{
        'role': 'system',
        'content': 'You are Sonia Bot, an AI assistant developed by Somwaki Developers. '
                   'You are working in Whatsapp and users can reach you by texting you here on whatsapp. They can pay '
                   'for the services by sending the message "/pay" after which an STK Push is sent to their phone, then'
                   ' they will enter their M-Pesa pin to confirm payment and once we receive it, you will send them a '
                   'confirmation message. They can then use you services for a whole month. You are a helpful assistant'
                   ' who can help them do their assignments, research and having fun. You are polite and give short and'
                   'precise responses. You can not work with images or other media except text only'
    }]
    history_messages = [
        {'role': msg[3], 'content': msg[4]} for msg in history if msg[3] in ['system', 'assistant', 'user']]
    return system_msg + history_messages


def is_premium(msisdn):
    last_payment = get_last_payment(msisdn)
    if not last_payment:
        return False
    last_amount = last_payment.amount
    return last_amount == 150
    # if premium:
    #     add_premium(msisdn)


def get_api_key(premium=False):
    if premium:
        resp = get_paid_for_key()
        if not resp:
            logger.error('ERROR: No key was found. ')
            raise NotImplementedError('API Keys were not found in database')
        key = resp.key
    else:
        conf = cfg_load.load(config_path)
        key = random.choice(conf.get('keys'))
    if not key:
        logger.error('ERROR: No key was found. ')
        raise NotImplementedError('API Keys were not found on configs')
    return key


def generate_response(chat_history: List[Dict], current_prompt: str, premium=False):
    api_key = get_api_key(premium)
    chat_history.append({'role': 'user', 'content': current_prompt})
    logger.info(f"Generating response: api_key -> {api_key} history_length -> {len(chat_history)} ...")
    response = openai.ChatCompletion.create(
        api_key=api_key,
        model=os.getenv('GPT-MODEL'),
        messages=chat_history
    )

    return response['choices'][0]['message']['content']


def can_get_response(msisdn, client_id, version):
    if not msisdn.startswith('254'):
        # send_notification(client_id, msisdn, message='The bot is temporarily not available in your country. '
        #                                             'We are working to restore services. Kindly check back later')
        return bool(int(os.getenv('ALLOW_NON_KENYANS', '0'))), False
    credits_count = int(check_paid_status(msisdn))
    logger.info(f'Credits Balance : {credits_count}')
    if credits_count == -1:
        return True, True
    if credits_count > 0:
        return True, False
    if credits_count == -2:
        notify_trial_period_over(msisdn, client_id, version)
    elif credits_count == -5:
        notify_subscription_expired_renew(msisdn, client_id, version)
    else:
        notify_depleted_free_responses(msisdn, client_id, version)
    return False, False


def notify_depleted_free_responses(msisdn, client_id, version):
    if add_depleted(msisdn):
        # notify the user that their credits have depleted or expired
        logger.info(f"user ({msisdn}) Credits have been depleted. Notifying user using client id: {client_id}")
        currency = get_upgrade_amount(msisdn)
        content = DEPLETED_CREDITS_MESSAGE.format(
            default_number=msisdn,
            upgrade_amount=currency.amount,
            symbol=currency.symbol
        )
        send_notification(
            client_id=client_id,
            msisdn=msisdn,
            session_id=get_session_id(client_id, msisdn),
            message=content,
            version=version
        )
        return
    logger.info(f"user ({msisdn}) Credits have been depleted and has already been notified")


def notify_trial_period_over(msisdn, client_id, version):
    if add_to_expired_and_notified(msisdn):
        # notify the user that their trial period is over
        logger.info(f"user ({msisdn}) trial period is over. Notifying user using client id: {client_id}")
        currency = get_upgrade_amount(msisdn)
        content = TRIAL_PERIOD_OVER.format(
            upgrade_amount=currency.amount,
            symbol=currency.symbol
        )
        send_notification(client_id=client_id, msisdn=msisdn, version=version, message=content)
        return
    logger.info(f"user ({msisdn}) trial period is over and has already been notified")


def notify_subscription_expired_renew(msisdn, client_id, version):
    if add_to_subscription_expired_and_notified(msisdn):
        # notify the user that their subscription is over, and they should renew
        logger.info(f"user ({msisdn}) subscription has expired. Notifying user using client id: {client_id}")
        currency = get_upgrade_amount(msisdn)
        content = RENEW_SUBSCRIPTION_MESSAGE.format(
            upgrade_amount=currency.amount,
            symbol=currency.symbol
        )
        send_notification(client_id, msisdn, message=content, version=version)

        return
    logger.info(f"user ({msisdn}) subscription has expired and has already been notified")


def handle_prompt(msisdn, text, client_id, version=2):
    rk = f'{client_id}:{msisdn}'
    if r.hexists(BOT_NUMBERS, msisdn):
        logger.error('-----------cannot process requests by bots----------')
        return
    if msisdn in os.getenv('BLOCKED_USERS').split(","):
        return

    if int(os.getenv('ENABLE_FREE_MODE', 1)):
        logger.info("FREE MODE ACTIVATED")
        has_credits, has_paid = True, True
    else:
        has_credits, has_paid = can_get_response(msisdn, client_id, version)

    if not has_credits:
        # user has no credits.
        logger.info("User has no free credits. Nothing to do...")
        return

    is_prem = is_premium(msisdn)
    if os.getenv('ENABLE_FREE_MODE', '1'):
        logger.info("FREE MODE ACTIVATED")
        is_prem = True
    logger.info(f"#### user is premium -> {is_prem}")
    try:
        response = generate_response(get_history(client_id, msisdn), text, premium=is_prem)
        logger.info(f'response: {response}')
        if 'goodbye' in response:
            sn_id = str(datetime.datetime.now().timestamp())
            r.set(rk, sn_id)
    except Exception as e:
        logger.error(e)

        overloaded = 'That model is currently overloaded with other requests'
        rate_limit = 'Rate limit reached'
        string_list = [overloaded, rate_limit]

        pattern = '|'.join(string_list)
        if re.search(pattern, str(e)):
            send_notification(client_id, msisdn, message=ERROR_GENERATING_RESPONSE, version=version)
            sn_id = str(datetime.datetime.now().timestamp())
            r.set(rk, sn_id)
            raise

    else:
        _session_id = get_session_id(client_id, msisdn)
        new_msgs = [
            {'role': 'user', 'content': text, 'msisdn': msisdn,
             'session_id': _session_id, 'client_id': client_id},
        ]
        save_messages(new_msgs)
        decrement_response_count(msisdn)
        high.enqueue(send_message_base, args=(
            client_id,
            msisdn,
            response,
            version,
            _session_id,
            'assistant'))

        adverts_queue.enqueue_in(
            time_delta=datetime.timedelta(seconds=SECONDS_BEFORE_ADVERT),
            func=send_advert,
            args=(msisdn, client_id, _session_id, version)
        )
        return response

