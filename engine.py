import datetime
import os
import random
import re
from typing import List, Dict

import cfg_load
import openai

from constants import DEPLETED_CREDITS_MESSAGE, UPGRADE_AMOUNT, engine, r, config_path, high, BOT_NUMBERS, \
    TRIAL_PERIOD_OVER, RENEW_SUBSCRIPTION_MESSAGE, logger, ERROR_GENERATING_RESPONSE
from crud import get_messages, save_messages
from db import metadata
from helpers import check_paid_status, add_depleted, get_session_id, decrement_response_count, \
    add_to_expired_and_notified, send_notification, add_to_subscription_expired_and_notified
from wp import send_message_base

metadata.create_all(engine)


def get_history(client_id, msisdn):
    session_id = get_session_id(client_id, msisdn)
    history = get_messages(session_id)
    system_msg = [{
        'role': 'system',
        'content': 'You are Sonia Bot, an AI assistant developed by Somwaki and Glemison Developers. '
                   'You are working in Whatsapp and users can reach you by texting you here on whatsapp. They can pay '
                   'for the services by sending the message "/pay" after which an STK Push is sent to their phone, then'
                   ' they will enter their M-Pesa pin to confirm payment and once we receive it, you will send them a '
                   'confirmation message. They can then use you services for a whole month. You are a helpful assistant'
                   ' who can help them do their assignments, research and having fun. You are polite and give short and'
                   'precise responses'
    }]
    history_messages = [
        {'role': msg[3], 'content': msg[4]} for msg in history if msg[3] in ['system', 'assistant', 'user']]
    return system_msg + history_messages


def get_api_key():
    conf = cfg_load.load(config_path)
    key = random.choice(conf.get('keys'))
    if not key:
        logger.error('ERROR: No key was found. ')
        raise NotImplementedError('API Keys were not found on configs')
    return key


def generate_response(chat_history: List[Dict], current_prompt: str):
    api_key = get_api_key()
    chat_history.append({'role': 'user', 'content': current_prompt})
    logger.info(f"Generating response: api_key -> {api_key} history_length -> {len(chat_history)} ...")
    response = openai.ChatCompletion.create(
        api_key=api_key,
        model=os.getenv('GPT-MODEL'),
        messages=chat_history
    )

    return response['choices'][0]['message']['content']


def can_get_response(msisdn, client_id):
    if not msisdn.startswith('254'):
        send_notification(client_id, msisdn, message='The bot is temporarily not available in your country. '
                                                     'We are working to restore services. Kindly check back later')
        return bool(int(os.getenv('ALLOW_NON_KENYANS', '0')))
    credits_count = int(check_paid_status(msisdn))
    logger.info(f'Credits Balance : {credits_count}')
    if credits_count == -1 or credits_count > 0:
        return True
    if credits_count == -2:
        notify_trial_period_over(msisdn, client_id)
    elif credits_count == -5:
        notify_subscription_expired_renew(msisdn, client_id)
    else:
        notify_depleted_free_responses(msisdn, client_id)
    return False


def notify_depleted_free_responses(msisdn, client_id):
    if add_depleted(msisdn):
        # notify the user that their credits have depleted or expired
        logger.info(f"user ({msisdn}) Credits have been depleted. Notifying user using client id: {client_id}")
        content = DEPLETED_CREDITS_MESSAGE.format(default_number=msisdn, upgrade_amount=UPGRADE_AMOUNT)
        send_notification(client_id, msisdn, session_id=get_session_id(client_id, msisdn), message=content)
        return
    logger.info(f"user ({msisdn}) Credits have been depleted and has already been notified")


def notify_trial_period_over(msisdn, client_id):
    if add_to_expired_and_notified(msisdn):
        # notify the user that their trial period is over
        logger.info(f"user ({msisdn}) trial period is ver. Notifying user using client id: {client_id}")
        content = TRIAL_PERIOD_OVER
        send_notification(client_id, msisdn, message=content)
        return
    logger.info(f"user ({msisdn}) trial period is over and has already been notified")


def notify_subscription_expired_renew(msisdn, client_id):
    if add_to_subscription_expired_and_notified(msisdn):
        # notify the user that their subscription is over, and they should renew
        logger.info(f"user ({msisdn}) subscription has expired. Notifying user using client id: {client_id}")
        content = RENEW_SUBSCRIPTION_MESSAGE
        send_notification(client_id, msisdn, message=content)

        return
    logger.info(f"user ({msisdn}) subscription has expired and has already been notified")


def handle_prompt(msisdn, text, client_id):
    rk = f'{client_id}:{msisdn}'
    if r.hexists(BOT_NUMBERS, msisdn):
        logger.error('-----------cannot process requests by bots----------')
        return
    if msisdn in os.getenv('BLOCKED_USERS').split(","):
        return
    if not can_get_response(msisdn, client_id):
        return

    try:
        response = generate_response(get_history(client_id, msisdn), text)
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
            send_notification(client_id, msisdn, message=ERROR_GENERATING_RESPONSE)
            return ''

        sn_id = str(datetime.datetime.now().timestamp())
        r.set(rk, sn_id)
        return ''
    else:
        new_msgs = [
            {'role': 'user', 'content': text, 'msisdn': msisdn,
             'session_id': get_session_id(client_id, msisdn), 'client_id': client_id},
            {'role': 'assistant', 'content': response, 'msisdn': msisdn,
             'session_id': get_session_id(client_id, msisdn), 'client_id': client_id},
        ]
        decrement_response_count(msisdn)
        high.enqueue(send_message_base, args=(client_id, msisdn, response))
        save_messages(new_msgs)
        return response
