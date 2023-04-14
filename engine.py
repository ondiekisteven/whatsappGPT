import datetime
import logging.config
import random
from typing import List, Dict

import cfg_load
import openai

from constants import DEPLETED_CREDITS_MESSAGE, UPGRADE_AMOUNT, engine, r, config_path, high
from crud import get_messages, save_messages
from db import metadata
from helpers import check_paid_status, add_depleted, get_session_id, decrement_response_count
from wp import send_message_base

logger = logging.getLogger(__name__)
metadata.create_all(engine)


def get_history(client_id, msisdn):
    session_id = get_session_id(client_id, msisdn)
    history = get_messages(session_id)
    system_msg = [{'role': 'system', 'content': 'You are Sonia Bot, an AI assistant developed by Somwaki and Glemison '
                                                'Developers. You are a helpful assistant'}]
    history_messages = [{'role': msg[3], 'content': msg[4]} for msg in history]
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
    response = openai.ChatCompletion.create(
        api_key=api_key,
        model="gpt-3.5-turbo",
        messages=chat_history
    )

    return response['choices'][0]['message']['content']


def can_get_response(msisdn):
    credits_count = int(check_paid_status(msisdn))
    if credits_count == -1 or credits_count > 0:
        return True
    return False


def notify_depleted_free_responses(msisdn, client_id):
    if add_depleted(msisdn):
        # notify the user that their credits have depleted or expired
        logger.info(f"user ({msisdn}) Credits have been depleted. Notifying user using client id: {client_id}")
        content = DEPLETED_CREDITS_MESSAGE.format(default_number=msisdn, upgrade_amount=UPGRADE_AMOUNT)
        high.enqueue(send_message_base, args=(
            client_id, msisdn, content))
        new_msgs = [
            {'role': 'notification', 'content': content, 'msisdn': msisdn, 'session_id': get_session_id(
                client_id, msisdn), 'client_id': client_id},
        ]
        save_messages(new_msgs)
        return
    logger.info(f"user ({msisdn}) Credits have been depleted and has already been notified")


def handle_prompt(msisdn, text, client_id):
    rk = f'{client_id}:{msisdn}'

    if not can_get_response(msisdn):
        notify_depleted_free_responses(msisdn, client_id)
        return

    try:
        response = generate_response(get_history(client_id, msisdn), text)
        logger.info(f'response: {response}')
        if 'goodbye' in response:
            sn_id = str(datetime.datetime.now().timestamp())
            r.set(rk, sn_id)
    except Exception as e:
        logger.error(e)
        sn_id = str(datetime.datetime.now().timestamp())
        r.set(rk, sn_id)
        return 'Hello! How can I assist you today?'
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
