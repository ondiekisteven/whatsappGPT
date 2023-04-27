import json
import logging
import os

import requests
from dotenv import load_dotenv

logger = logging.getLogger('whatsapp')

load_dotenv()


class Whatsapp:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.base_url = os.getenv('API_BASE_URL')
        self.token = None

        assert self.base_url is not None

    def send_request(self, payload, path, method, headers=None, params=None):

        r = requests.request(method, f'{self.base_url}{path}', params=params, headers=headers, json=payload)
        if r.status_code == 200:
            logger.info(f"200 -> {r.text}")
            return json.loads(r.text)
        logger.error(f'{r.status_code} -> {r.text}')
        return None

    def login(self):
        payload = {
            'username': self.username,
            'password': self.password
        }
        resp = self.send_request(payload, 'auth/', method='POST')
        token = resp.get('token')
        if token:
            self.token = token

    def send_message(self, chat_id, message):

        payload = {
            "receiver": chat_id,
            "text": message,
        }

        if self.token is None:
            self.login()
        headers = {'Authorization': f'Bearer {self.token}'}
        try:
            self.send_request(payload, 'messages/', 'POST', headers=headers)
        except Exception as e:
            logger.error(e)


def send_message_base(client_id, chat_id, message):
    headers = {
        'auth-key': os.getenv('API_AUTH_KEY'),
        'client_id': client_id
    }

    if len(chat_id) == 12:
        chat_id = f'{chat_id}@c.us'
    if '@' in chat_id:
        pass
    else:
        # is group stuff
        chat_id = f'{chat_id}@g.us'
    payload = {
        "chat_id": chat_id,
        "message": message,
        "type": "chat"
    }
    r = requests.post(os.getenv('WEBAPI_URL'), headers=headers, json=payload)
    if r.status_code == 200:
        logger.info(f"200 -> {r.text}")

    logger.error(f'{r.status_code} -> {r.text}')
    return None
