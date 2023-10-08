import os
import re

import requests

import crud
from constants import STK_PUSH_SENT_MESSAGE, high, logger, MALAWI_PAYMENT_REQUESTED_MESSAGE, phones_mapping
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


def handle_payment_kenya(msisdn, payment_no, client_id, version=2):
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


def handle_payment_malawi(msisdn, client_id, version=2):
    currency = get_upgrade_amount(msisdn)

    crud.save_malawi_waiting(msisdn, client_id, currency.amount, target=msisdn, version=version)

    resp_msg = MALAWI_PAYMENT_REQUESTED_MESSAGE.format(
        upgrade_amount=currency.amount,
        receiving_number=phones_mapping.get(msisdn[3], '265884749249')[0],
        receiving_name=phones_mapping.get(msisdn[3], 'Clara Banda')[1]
    )
    high.enqueue(send_message_base, args=(client_id, msisdn, resp_msg, version, get_session_id(
        client_id, msisdn), 'notification'))


def handle_pay_prompt(msisdn, text, client_id, version):
    if text.lower() in ['/pay', 'pay', '.pay']:
        payment_no = msisdn
    else:
        items = [d for d in text.split(' ') if d]
        payment_no = items[1]

    country_code, payment_no = parse_msisdn(payment_no)

    if country_code == 254:
        handle_payment_kenya(msisdn=msisdn, payment_no=payment_no, client_id=client_id, version=version)

    elif country_code == 265:
        handle_payment_malawi(msisdn=msisdn, client_id=client_id, version=version)


def extract_details(message):
    patterns = [
        r"Trans\.ID:\s+(\S+)[\s\S]+from\s+(\d+),(\w+\s\w+)\.[\s\S]+(\d+\.\d+)",
        r"Trans\.ID\s*:\s*(\S+)\..*?MK (\d+\.\d+) from (\d+),(\w+\s\w+)",
        r"Trans Id: (\S+), Money transfer to (\d+), (\w+\s\w+) is successful, Trans Amt: MK(\d+\.\d+)"
    ]
    details = None
    for pattern in patterns:
        matches = re.findall(pattern, message)

        if matches:
            trans_id, amount, msisdn, name = matches[0]

            details = {
                "transaction_id": trans_id,
                "msisdn": F"265{msisdn}",
                "name": name,
                "amount": amount
            }

            break

    return details
