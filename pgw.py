import json
import re
import uuid
from datetime import timedelta

from constants import *
from db import *
from helpers import *
from schema import *
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


def handle_payment_tanzania(msisdn, client_id, email, trx_ref, network, version=2):
    currency = get_upgrade_amount(msisdn)

    crud.save_tanzania_waiting(
        msisdn, client_id, currency.amount, target=msisdn, trx_ref=trx_ref, email=email, full_name='', version=version)

    resp_msg = TANZANIA_PAYMENT_REQUESTED_MESSAGE.format(
        phone_number=msisdn,
    )

    high.enqueue(send_message_base, args=(client_id, msisdn, resp_msg, version, get_session_id(
        client_id, msisdn), 'notification'))

    url = 'https://api.flutterwave.com/v3/charges?type=mobile_money_tanzania'
    headers = {
        'Authorization': 'Bearer FLWSECK-3ad88b0119820d5199f5a3fe93c5783d-18ce93ac61cvt-X'
    }
    amount = get_upgrade_amount(msisdn)
    body = {
        "tx_ref": trx_ref,
        "amount": amount.amount,
        "currency": "TZS",
        "network": network,
        "email": email,
        "phone_number": msisdn,
        "fullname": msisdn
    }

    resp = requests.post(url, headers=headers, json=body)
    logger.info(f"TZ STK PUSH: {resp.text}")


def initiate_payment_malawi(trx_ref, amount, network, email, phone, name, token, currency='MWK', url=None):
    payload = {
        "tx_ref": trx_ref,
        "amount": amount,
        "currency": currency,
        "network": network,
        "email": email,
        "phone_number": phone,
        "fullname": name
    }

    headers = {
        'Authorization': f'Bearer {token}'
    }

    resp = requests.post(url, json=payload, headers=headers)

    if resp.status_code == 200:
        # --------- sample success response -----------
        # {
        #     "status": "success",
        #     "message": "Charge initiated",
        #     "meta": {
        #         "authorization": {
        #             "redirect": "https://checkout.flutterwave.com/captcha/verify/lang-en/5350253:a53cb801ffe7c8",
        #             "mode": "redirect"
        #         }
        #     }
        # }
        json_resp = json.loads(resp.text)
        logger.info(f"Charge Initialization response: {resp.text}")
        payment_url = json_resp['meta']['authorization']['redirect']
        return payment_url, json_resp

    logger.info(f"Unsuccessful response: {resp.status_code} -> {resp.text}")


def handle_payment_malawi_send_money(msisdn, client_id, version=2):
    currency = get_upgrade_amount(msisdn)

    crud.save_malawi_waiting(msisdn, client_id, currency.amount, target=msisdn, version=version)

    resp_msg = MALAWI_PAYMENT_REQUESTED_MESSAGE.format(
        upgrade_amount=currency.amount,
        receiving_number=phones_mapping.get(msisdn[3], '265884749249')[0],
        receiving_name=phones_mapping.get(msisdn[3], 'Clara Banda')[1]
    )
    high.enqueue(send_message_base, args=(client_id, msisdn, resp_msg, version, get_session_id(
        client_id, msisdn), 'notification'))


def handle_payment_malawi(msisdn, client_id, version=2):
    currency = get_upgrade_amount(msisdn)

    if msisdn[3] in ['8', '9']:
        return handle_payment_malawi_send_money(msisdn, client_id, version)
    trx_ref = f"MLW-{str(datetime.now().timestamp()).split('.')[0]}-{msisdn}"
    network = malawi_network_mapping.get(msisdn[3])

    url, payload = initiate_payment_malawi(
        trx_ref=trx_ref,
        amount=currency.amount,
        network=network,
        email=f'sonia_{msisdn}@somwaki.com',
        phone=msisdn,
        name=msisdn,
        token=os.getenv('FLUTTERWAVE_TOKEN'),
        url='https://api.flutterwave.com/v3/charges?type=mobile_money_malawi'
    )
    if url:
        crud.save_malawi_flutter_waiting(
            msisdn=msisdn,
            client_id=client_id,
            amount=currency.amount,
            target=msisdn,
            version=version,
            payment_url=url,
            trx_ref=trx_ref,
            network=network,
            payload=json.dumps(payload),
            trx_id=None
        )
        resp_msg = MALAWI_PAYMENT_REQUESTED_MESSAGE_V2.format(
            payment_url=url
        )
    else:
        resp_msg = MALAWI_PAYMENT_REQUEST_FAILED_V2

    high.enqueue(send_message_base, args=(client_id, msisdn, resp_msg, version, get_session_id(
        client_id, msisdn), 'notification'))


def get_tz_telco(msisdn):
    for category, pattern, in TZ_TELCO_REGEX.items():
        if re.match(pattern, msisdn):
            return category


def handle_pay_prompt(msisdn, text, client_id, version):
    if text.lower() in ['/pay', 'pay', '.pay', '"pay"', '"/pay"', "'pay'", "'/pay'"]:
        payment_no = msisdn
    else:
        items = [d for d in text.split(' ') if d]
        payment_no = items[1]

    country_code, payment_no = parse_msisdn(payment_no)

    if country_code == 254:
        handle_payment_kenya(msisdn=msisdn, payment_no=payment_no, client_id=client_id, version=version)

    elif country_code == 265:
        handle_payment_malawi(msisdn=msisdn, client_id=client_id, version=version)

    elif country_code == 255:
        tz_telco = get_tz_telco(msisdn)
        logger.info(f'TZ TELCO: {tz_telco}')
        handle_payment_tanzania(msisdn=msisdn, client_id=client_id, version=version, email=f"{msisdn}@somwaki.com",
                                trx_ref=uuid.uuid4().hex, network=tz_telco)


def extract_details(message):
    message = message.replace("\\n", "")
    message = message.replace("\n", "")
    patterns = [
        r"Trans\.ID : (?P<transaction_id>[\w\.]+)\. .*received MK (?P<amount>\d+\.\d+) from (?P<msisdn>\d+),(?P<name>[A-Za-z\s']+)\. .*",
        r"Money Received from (?P<msisdn>[\d]+) (?P<name>[A-Za-z\s]+) .*Amount: (?P<amount>[.,\d]+)MWK Ref: (?P<transaction_id>\w+).*",
        r"Trans\.ID: (?P<transaction_id>[\w\.]+) .* received MK (?P<amount>[\d]+) plus MK (?P<withdrawal>\d+) .* from 0(?P<msisdn>\d+),(?P<name>[A-Za-z ']+)\. .*"
    ]
    details = {
        "transaction_id": None,
        "msisdn": None,
        "name": None,
        "amount": None

    }
    for pattern in patterns:
        match = re.search(pattern, message)

        if match:
            amount = int(float(match.group('amount').replace(",", "")))
            if 'withdrawal' in match.groupdict():
                amount += int(float(match.groupdict().get('withdrawal').replace(",", "")))
                logger.info("withdrawal charges found.")

            details = {
                "transaction_id": match.group('transaction_id'),
                "msisdn": match.group('msisdn') if match.group('msisdn').startswith(
                    '265') else F"265{match.group('msisdn')}",
                "name": match.group('name'),
                "amount": amount
            }

            break

    return details['transaction_id'], details['msisdn'], details['name'], details['amount']


def handle_malawi_sms(from_, text, sent, received, sim):
    logger.info("-" * 100)
    try:
        saved = crud.save_new_received_sms(
            from_=from_,
            sms_text=text,
            sent_timestamp=sent,
            received_timestamp=received,
            sim=sim
        )
        if not saved:
            logger.info("Not saved. Exiting")
            return {'error': 'message not saved'}

        transaction_id, msisdn, name, amount = extract_details(text)
        logger.info(f"transaction_id: {transaction_id}")
        logger.info(f"msisdn: {msisdn}")
        logger.info(f"name: {name}")
        logger.info(f"amount: {amount}")

        if transaction_id is None or amount is None:
            return {'message': 'success'}

        waiting = crud.get_malawi_waiting(msisdn, amount)
        if waiting:
            crud.mark_stk_waiting_fulfilled(waiting.id, table=MalawiPaymentsWaiting)
            client_id = waiting.client_id
            target = waiting.target
            version = waiting.version
            notify = True
        else:
            logger.warning("Payment has no matching waiting record. Using Default Client ID")
            client_id = os.getenv('DEFAULT_CLIENT_ID')
            target = msisdn
            version = 2
            notify = True

        expiry = datetime.now() + timedelta(days=30)
        current_expiry = get_user_expiry(target)
        if current_expiry:
            current_expiry_datetime = datetime.fromtimestamp(current_expiry)
            if current_expiry_datetime > datetime.now(): 
                logger.info("User already has a future expiry. Extending that.")
                expiry = current_expiry_datetime + timedelta(days=30)

        added = add_paid(target, expiry.timestamp())
        logger.info(f"Adding to paid users: target -> {target}, expiry -> {expiry}, added -> {added}")

        payment = PaymentBase(
            amount=int(float(amount)),
            msisdn=msisdn,
            trx_id=transaction_id,
            request_dump=json.dumps(
                {'transaction_id': transaction_id, 'msisdn': msisdn, 'name': name, 'amount': amount}
            ),
            channel=from_
        )
        crud.save_malawi_payment(payment)

        logger.info(f"Sending notification to {target} using {client_id}")
        if payment.amount != MALAWI_UPGRADE_AMOUNT:
            logger.info("Not sending notification .")
            return {'message': 'success'}
        if notify:
            send_notification(
                client_id,
                payment.msisdn,
                version,
                get_session_id(client_id, payment.msisdn),
                MALAWI_PAYMENT_RECEIVED_MESSAGE.format(
                    amount=payment.amount,
                    msisdn=payment.msisdn,
                    trx_id=payment.trx_id,
                    expiry=expiry.strftime("%d/%m/%Y, %H:%M")
                )
            )

            # sending notification to payments group
            msg = "{} --> {}".format(
                payment.msisdn,
                MALAWI_PAYMENT_RECEIVED_MESSAGE.format(
                    amount=payment.amount,
                    msisdn=payment.msisdn,
                    trx_id=payment.trx_id,
                    expiry=expiry.strftime("%d/%m/%Y, %H:%M")
                )
            )
            send_notification(
                client_id,
                '120363284516165905@g.us',
                version,
                get_session_id(client_id, payment.msisdn),
                msg
            )

        logger.info("-" * 100)
        return {'message': 'success'}
    except Exception as x:
        logger.exception(x)

        logger.info("-" * 100)
        return {'error': str(x)}


country_functions_mapping = {
    265: {
        'get_waiting_fxn': crud.get_malawi_flutter_waiting,

    }
}


def handle_malawi_webhook(phone_number, amount, status, trx_ref, data, event_type, flw_ref):
    waiting = crud.get_malawi_flutter_waiting(phone_number, amount)
    if waiting:
        logger.info(f"Waiting record found: {waiting}")
        crud.mark_stk_waiting_fulfilled(waiting.id, table=MalawiFlutterPaymentsWaiting)
        client_id = waiting.client_id
        target = waiting.target
        version = waiting.version
        notify = True
    else:
        logger.warning("Payment has no matching waiting record. Using Default Client ID")
        client_id = os.getenv('DEFAULT_CLIENT_ID')
        target = phone_number
        version = 2
        notify = True
    expiry = None
    if status == 'successful':
        expiry = datetime.now() + timedelta(days=30)
        current_expiry = get_user_expiry(target)
        if current_expiry:
            current_expiry_datetime = datetime.fromtimestamp(current_expiry)
            if current_expiry_datetime > datetime.now(): 
                logger.info("User already has a future expiry. Extending that.")
                expiry = current_expiry_datetime + timedelta(days=30)
        
        expiry_timestamp = expiry.timestamp()
        logger.info(f"expiry: {expiry_timestamp}")
        added = add_paid(target, expiry_timestamp)
        logger.info(f"Adding to paid users: target -> {target}, expiry -> {expiry_timestamp}, added -> {added}")

    payment = FlutterwavePayment(
        amount=int(float(amount)),
        msisdn=phone_number,
        trx_id=trx_ref,
        request_dump=json.dumps(data),
        channel=event_type,
        client_id=client_id,
        target=phone_number,
        event_type=event_type,
        status=status,
        flw_ref=flw_ref,
        version=version
    )
    crud.save_flutter_malawi_payment(payment)

    if payment.amount < MALAWI_UPGRADE_AMOUNT:
        logger.info("Not sending notification .")
        return {'message': 'success'}
    if notify and status == 'successful':
        logger.info(f"Sending notification to {target} using {client_id}")
        send_notification(
            client_id,
            payment.msisdn,
            version,
            get_session_id(client_id, payment.msisdn),
            MALAWI_PAYMENT_RECEIVED_MESSAGE.format(
                amount=payment.amount,
                msisdn=payment.msisdn,
                trx_id=payment.trx_id,
                expiry=expiry.strftime("%d/%m/%Y, %H:%M")
            )
        )

        # sending notification to payments group
        msg = "{} --> {}".format(
            payment.msisdn,
            MALAWI_PAYMENT_RECEIVED_MESSAGE.format(
                amount=payment.amount,
                msisdn=payment.msisdn,
                trx_id=payment.trx_id,
                expiry=expiry.strftime("%d/%m/%Y, %H:%M")
            )
        )
        send_notification(
            client_id,
            '120363284516165905@g.us',
            version,
            get_session_id(client_id, payment.msisdn),
            msg
        )



def handle_tanzania_webhook(phone_number, amount, status, trx_ref, data, event_type, flw_ref):
    waiting = crud.get_tanzania_flutter_waiting(phone_number, amount)
    if waiting:
        logger.info(f"Waiting record found: {waiting}")
        crud.mark_stk_waiting_fulfilled(waiting.id, table=TanzaniaPaymentsWaiting)
        client_id = waiting.client_id
        target = waiting.target
        version = waiting.version
        notify = True
    else:
        logger.warning("Payment has no matching waiting record. Using Default Client ID")
        client_id = os.getenv('DEFAULT_CLIENT_ID')
        target = phone_number
        version = 2
        notify = True
    expiry = None
    if status == 'successful':
        expiry = datetime.now() + timedelta(days=30)
        current_expiry = get_user_expiry(target)
        if current_expiry:
            current_expiry_datetime = datetime.fromtimestamp(current_expiry)
            if current_expiry_datetime > datetime.now(): 
                logger.info("User already has a future expiry. Extending that.")
                expiry = current_expiry_datetime + timedelta(days=30)

        expiry_timestamp = expiry.timestamp()
        logger.info(f"expiry: {expiry_timestamp}")
        added = add_paid(target, expiry_timestamp)
        logger.info(f"Adding to paid users: target -> {target}, expiry -> {expiry_timestamp}, added -> {added}")

    payment = FlutterwavePayment(
        amount=int(float(amount)),
        msisdn=phone_number,
        trx_id=trx_ref,
        request_dump=json.dumps(data),
        channel=event_type,
        client_id=client_id,
        target=phone_number,
        event_type=event_type,
        status=status,
        flw_ref=flw_ref,
        version=version
    )
    crud.save_flutter_payment(payment, table=TanzaniaFlutterPayments)

    if payment.amount < TANZANIA_UPGRADE_AMOUNT:
        logger.info("Not sending notification .")
        return {'message': 'success'}
    if notify and status == 'successful':
        logger.info(f"Sending notification to {target} using {client_id}")
        send_notification(
            client_id,
            payment.msisdn,
            version,
            get_session_id(client_id, payment.msisdn),
            TANZANIA_PAYMENT_RECEIVED_MESSAGE.format(
                amount=payment.amount,
                msisdn=payment.msisdn,
                trx_id=payment.trx_id,
                expiry=expiry.strftime("%d/%m/%Y, %H:%M")
            )
        )

        # sending notification to payments group
        msg = "{} --> {}".format(
            payment.msisdn,
            MALAWI_PAYMENT_RECEIVED_MESSAGE.format(
                amount=payment.amount,
                msisdn=payment.msisdn,
                trx_id=payment.trx_id,
                expiry=expiry.strftime("%d/%m/%Y, %H:%M")
            )
        )
        send_notification(
            client_id,
            '120363284516165905@g.us',
            version,
            get_session_id(client_id, payment.msisdn),
            msg
        )



def handle_flutterwave_webhook(data: dict):
    if 'event' in data and data['event'] == 'charge.completed':
        event_type = data['event.type']
        trx_ref = data['data']['tx_ref']
        amount = data['data']['amount']
        currency = data['data']['currency']
        phone_number = data['data']['customer']['phone_number']
        status = data['data']['status']
        flw_ref = data['data']['flw_ref']

        country_code, payment_no = parse_msisdn(phone_number)

        if country_code == 265:
            handle_malawi_webhook(
                phone_number, amount, status, trx_ref, data, event_type, flw_ref
            )

        elif country_code == 255:
            handle_tanzania_webhook(
                phone_number, amount, status, trx_ref, data, event_type, flw_ref
            )
        logger.info("-" * 100)
        return {'message': 'success'}

    logger.info("Received strange request...")
