import os

import requests

import crud
from constants import STK_PUSH_SENT_MESSAGE, high, logger
from helpers import get_session_id, parse_msisdn, get_upgrade_amount
from wp import send_message_base


class KopoKopo:
    def __init__(self):
        pass

    def get_key(self):
        pass


class TinyPesa:
    def __init__(self, api_key):
        self.api_key = api_key

    def stk_push(self, msisdn, amount):
        url = "https://tinypesa.com/api/v1/express/initialize"
        headers = {'accept': 'application/json', 'Apikey': self.api_key}
        body = {'amount': amount, 'msisdn': msisdn}
        try:
            response = requests.post(url, data=body, headers=headers)
            logger.info(f'STK push status code -> "{response.status_code}"')
            if response.status_code == 200:
                logger.info(f'Response: {response.text}')
                return True
        except Exception as e:
            logger.error(e)

        return False


def handle_pay_prompt(msisdn, text, client_id, version):
    if text.lower() in ['/pay', 'pay', '.pay']:
        payment_no = msisdn
    else:
        items = [d for d in text.split(' ') if d]
        payment_no = items[1]

    payment_no = parse_msisdn(payment_no)
    if not payment_no.startswith('254'):
        logger.warning(f'Payment request from number not from Kenya: {payment_no}')
        return

    logger.info("Sending stk push")
    currency = get_upgrade_amount(msisdn)

    success = TinyPesa(os.getenv('TINYPESA_API_KEY')).stk_push(payment_no, currency.amount)
    if success:
        # save to stk waiting... we'll use that to know which whatsapp account will be used to reply
        # ... and also who to give access once payment has been made

        crud.save_stk_waiting(msisdn=payment_no, client_id=client_id, amount=currency.amount, target=msisdn)

        # tell user we have sent stk push to them
        resp_msg = STK_PUSH_SENT_MESSAGE.format(phone_number=payment_no)
        high.enqueue(send_message_base, args=(client_id, msisdn, resp_msg, version, get_session_id(
            client_id, msisdn), 'notification'))
    else:
        resp_msg = 'Error sending stk push to your phone. Please try again after some time.'
        high.enqueue(send_message_base, args=(client_id, msisdn, resp_msg, version, get_session_id(
            client_id, msisdn), 'notification'))
