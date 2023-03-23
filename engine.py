import datetime
import logging.config
from typing import List, Dict

import cfg_load
import openai
import os
from redis import Redis
from rq import Queue
from sqlalchemy import select

from db import create_db, messages, metadata
from wp import Whatsapp

openai.api_key = os.getenv("OPENAI_API_KEY")
r = Redis(host=os.getenv('REDIS_HOST', 'localhost'), db=os.getenv('REDIS_DB', 5))
logging.config.fileConfig('logging.conf', disable_existing_loggers=False)

wa = Whatsapp(os.getenv('API_USERNAME'), os.getenv('API_PASSWORD'))
config_path = os.getenv('CONFIG_FILE', 'config.yaml')
try:
    confg = cfg_load.load(config_path)
except FileNotFoundError:
    raise NotImplementedError(
        "You have not specified a config file path. Default config name is 'config.yaml'")

high = Queue('high', connection=r)

logger = logging.getLogger('engine')
engine = create_db(confg['database'])
metadata.create_all(engine)


def get_db():
    return engine.connect()


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


def get_session_id(msisdn):
    sn_id = r.get(msisdn)
    if not sn_id:
        logger.info(f'{msisdn} has no active session id, creating one...')
        sn_id = str(datetime.datetime.now().timestamp())
        r.set(msisdn, sn_id)

    r.expire(msisdn, time=datetime.timedelta(minutes=int(os.getenv('SESSION_LENGTH_SECONDS', '3600'))))
    return sn_id


def get_history(msisdn):
    session_id = get_session_id(msisdn)
    history = get_messages(session_id)

    return [{'role': msg[3], 'content': msg[4]} for msg in history]


def generate_response(chat_history: List[Dict], current_prompt: str):
    chat_history.append({'role': 'user', 'content': current_prompt})
    response = openai.ChatCompletion.create(
      model="gpt-3.5-turbo",
      messages=chat_history
    )

    return response['choices'][0]['message']['content']


def handle_prompt(msisdn, text, client_id):
    try:
        response = generate_response(get_history(msisdn), text)
        logger.info(f'response: {response}')
    except Exception as e:
        logger.error(e)
        return None
    else:
        new_msgs = [
            {'role': 'user', 'content': text, 'msisdn': msisdn, 'session_id': get_session_id(msisdn)},
            {'role': 'system', 'content': response, 'msisdn': msisdn, 'session_id': get_session_id(msisdn)},
        ]

        save_messages(new_msgs)
        high.enqueue(Whatsapp.send_message_base, args=(client_id, msisdn, response))
        return response
