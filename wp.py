import json
import logging
import os
import urllib.parse

import requests
from dotenv import load_dotenv

from crud import save_messages

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


class V2Whatsapp:
    def __init__(self, base_url, key):
        self.url = base_url
        self.key = key

    def _send_request(self, method, path, json_=None, data=None, headers=None, files=None, params=None):
        # if method == 'POST':
        #     assert json is not None, 'You have not provided json body to be sent'

        if files:
            headers['Content-Type'] = 'multipart/form-data'

        url = f'{self.url}{path}{params}'

        try:
            resp = requests.request(
                method=method.upper(), url=url, json=json_, data=data, headers=headers, files=files,
            )
            logger.info(f"REQUEST [{method} {url}] {resp.request.__dict__} ")
            logger.info(f"RESPONSE [{resp.status_code}] {resp.text}")
            return resp
        except Exception as x:
            logger.exception(x)
            logger.error(f"Error sending request, {str(x)}")
            raise

    def send_text_message(self, receiver: str, message: str):
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        payload = {
            'id': receiver,
            'message': message
        }
        data = urllib.parse.urlencode(payload)
        params = f'?key={self.key}'

        resp = self._send_request('POST', '/message/text', data=data, headers=headers, params=params)
        logger.info("SENT MESSAGE")

        return resp


def _send_message_base(client_id, chat_id, message, version):
    if version == 2:
        return send_msg_new(client_id, chat_id, message)
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
        return
    logger.error(f'{r.status_code} -> {r.text}')
    return None


def send_message_base(client_id, chat_id, message, version, session_id, role):
    send_resp: dict = _send_message_base(client_id, chat_id, message, version)

    new_msgs = [
        {'role': role,
         'content': message,
         'msisdn': chat_id,
         'session_id': session_id,
         'client_id': client_id,
         'message_id': send_resp['data']['key']['id'] if 'data' in send_resp and 'key' in send_resp['data'] else "",
         'success': not send_resp['error'] if 'error' in send_resp else False
         }
    ]
    save_messages(new_msgs)
    return send_resp


def send_msg_new(client_id, chat_id, message):
    url = os.getenv('V2_BASE_URL', 'http://new_whatsapp:3333')
    whatsapp = V2Whatsapp(base_url=url, key=client_id)

    resp = whatsapp.send_text_message(chat_id.split("@")[0], message)
    logger.info(f'{resp.status_code} -> {resp.text}')
    try:
        json_resp = json.loads(resp.text)
    except:
        json_resp = resp.text

    return json_resp
