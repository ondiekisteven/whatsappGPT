import json
import logging
import os
from datetime import timedelta, datetime

import openai
import requests
from flask import Flask, request, jsonify
from rq import Queue, Retry

import crud
from constants import PAYMENT_RECEIVED_MESSAGE, BOT_NUMBERS, MALAWI_PAYMENT_RECEIVED_MESSAGE
from db import malawi_payments_waiting
from engine import r, handle_prompt
from helpers import send_notification, get_session_id, add_paid, parse_msisdn, add_simulated_msg_id, \
    handle_referral_msg, handle_getting_code, handle_lesson_subscription
from pgw import handle_pay_prompt, extract_details
from schema import PaymentBase

logger = logging.getLogger(__name__)

app = Flask(__name__)
openai.api_key = os.getenv("OPENAI_API_KEY")
q = Queue('default', connection=r)


@app.route('/test', methods=['GET'])
def test():
    return {'message': 'success'}


def forward_payment(payload, url):
    logger.info(f"Forwarding TinyPesa Request: payload -> {payload}, url -> {url}")
    req = requests.post(url, json=payload, verify=False)
    logger.info(f"Response code -> {req.status_code} response body -> {req.text}")


@app.route('/sms-webhook', methods=['POST'])
def sms_webhook_view():
    data = request.json

    logger.info("-----Received new sms-webhook request----")
    logger.info(data)
    try:
        crud.save_new_received_sms(
            from_=data['from'],
            sms_text=data['text'],
            sent_timestamp=data['sentStamp'],
            received_timestamp=data['receivedStamp'],
            sim=data['sim']
        )

        payment_data = extract_details(data['text'])
        logger.info(f"Payment Data: {payment_data}")

        if payment_data is None:
            return {'message': 'success'}

        if not payment_data['transaction_id'] or not payment_data['amount']:
            logger.info("No data was found for this transaction")
            return {'message': 'success'}

        waiting = crud.get_malawi_waiting(payment_data['msisdn'], payment_data['amount'])
        if waiting:
            crud.mark_stk_waiting_fulfilled(waiting.id, table=malawi_payments_waiting)
            client_id = waiting.client_id
            target = waiting.target
            version = waiting.version
            notify = True
        else:
            logger.warning("Payment has no matching waiting record. Using Default Client ID")
            client_id = os.getenv('DEFAULT_CLIENT_ID')
            target = payment_data['msisdn']
            version = 2
            notify = False

        payment = PaymentBase(
            amount=int(float(payment_data['amount'])),
            msisdn=payment_data['msisdn'],
            trx_id=payment_data['transaction_id'],
            request_dump=json.dumps(json.dumps(payment_data)),
            channel=data['from']
        )
        crud.save_malawi_payment(payment)
        expiry = datetime.now() + timedelta(days=30)
        add_paid(target, expiry)

        # if not notify and bool(os.getenv('IGNORE_STRAY_MESSAGES', '1')):
        #     logger.info("No matching waiting was found. Not sending notification")
        #     return {'message': 'success'}
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
        return {'message': 'success'}
    except Exception as x:
        logger.exception(x)
        return {'message': 'success'}


@app.route('/index', methods=['POST'])
def sms_index():
    data = request.json

    logger.info("-----Received new index sms request----")
    logger.info(data)
    try:
        crud.save_index_sms(
            from_=data['from'],
            sms_text=data['text'],
            sent_timestamp=data['sentStamp'],
            received_timestamp=data['receivedStamp'],
            sim=data['sim']
        )
        return {'message': 'success'}
    except Exception as x:
        logger.exception(x)
        raise


@app.route('/payment', methods=['POST'])
def payment_view():

    req = request.json
    if isinstance(req, dict) and 'Body' in req and 'stkCallback' in req['Body']:
        # is tiny pesa payment
        if os.getenv('FORWARD_PAYMENTS_URL'):
            q.enqueue(forward_payment, args=(req, os.getenv('FORWARD_PAYMENTS_URL')))

        if 'CallbackMetadata' not in req['Body']['stkCallback']:
            error_desc = req['Body']['stkCallback']['ResultDesc']
            error_msisdn = req['Body']['stkCallback']['Msisdn']
            error_amount = req['Body']['stkCallback']['Amount']
            waiting = crud.get_stk_waiting(error_msisdn, error_amount)
            if waiting:
                client_id = waiting.client_id
                reply_to = waiting.target
            else:
                client_id = os.getenv('DEFAULT_CLIENT_ID')
                reply_to = error_msisdn

            send_notification(
                version=waiting.version,
                client_id=client_id,
                msisdn=reply_to,
                session_id=get_session_id(client_id, error_msisdn),
                message=f'*An Error Occurred When Processing Your Payment:*: \n\n\n{error_desc}',
            )
            if reply_to != error_msisdn:
                send_notification(
                    version=waiting.version,
                    client_id=client_id,
                    msisdn=error_msisdn,
                    session_id=get_session_id(client_id, error_msisdn),
                    message=f'*An Error Occurred When Processing Your Payment:*: \n\n\n{error_desc}'
                )
            # is not a successful payment
            return {'message': 'success'}
        payment = PaymentBase(
            amount=req['Body']["stkCallback"]['Amount'],
            msisdn=req['Body']["stkCallback"]['Msisdn'],
            trx_id=[x['Value'] for
                    x in req['Body']['stkCallback']['CallbackMetadata']['Item']
                    if x['Name'] == 'MpesaReceiptNumber'][0],
            request_dump=json.dumps(req),
            channel='MPESA'
        )
        logger.info("------processing payment: ")
        logger.info(payment.dict())

        # create new payment
        try:
            crud.save_payment(payment)
            waiting = crud.get_stk_waiting(payment.msisdn, payment.amount)
            if waiting:
                crud.mark_stk_waiting_fulfilled(waiting.id)
                client_id = waiting.client_id
                target = waiting.target
                version = waiting.version
            else:
                logger.warning("Payment has no matching waiting record. Using Default Client ID")
                client_id = os.getenv('DEFAULT_CLIENT_ID')
                target = payment.msisdn
                version = 2

            logger.info(f"Adding {target} to paid users")

            now = datetime.strptime(str([x['Value'] for
                                         x in req['Body']['stkCallback']['CallbackMetadata']['Item']
                                         if x['Name'] == 'TransactionDate'][0]), '%Y%m%d%H%M%S')
            expiry = now + timedelta(days=30)
            add_paid(target, expiry)
            logger.info(f"Sending notification to {target} using {client_id}")
            send_notification(
                client_id,
                payment.msisdn,
                version,
                get_session_id(client_id, payment.msisdn),
                PAYMENT_RECEIVED_MESSAGE.format(
                    amount=payment.amount,
                    msisdn=payment.msisdn,
                    trx_id=payment.trx_id,
                    expiry=expiry.strftime("%d/%m/%Y, %H:%M")
                )
            )
        except Exception as x:
            logger.exception(x)
            logger.warning('A Db Error Occurred when saving payment. ')
    else:
        # handle mpesa req here...
        logger.warning("--------------------------------------")
        logger.warning("-----------unknown payment------------")
        logger.warning(req)
        logger.warning("--------------------------------------")

    return {'message': 'success'}


@app.route("/", methods=("GET", "POST"))
def index():
    if request.method == "POST":
        d = request.json
        # q.enqueue(update_clients, d)
        from_ = d.get('from') or ''
        body = d.get('body')
        client_id = d.get('client_id')
        logger.info(f"request: from -> {from_}, body -> {body} -> client_id -> {client_id}")
        if not body or not from_:
            return jsonify({'error': 'Invalid Content'})

        if 'g.us' in from_:
            if from_ not in os.environ.get('SUPPORT_GROUPS', '120363127313593286@g.us').split(','):
                return jsonify({'message': 'not handling groups'})
            sim_values = [d for d in body.split(' ') if d]
            sim_no = sim_values[0]
            _, from_ = parse_msisdn(sim_no, log=False)
            if not from_:
                return jsonify({'message': 'not handling groups'})
            from_ += '@c.us'
            body = ' '.join(sim_values[1:])

            # get client_id from the author of the message
            author = d.get('author').split('@')[0]
            client_id = r.hget(BOT_NUMBERS, author)
            if not client_id:
                logger.error(f'No client id found for simulated message. author -> {author}')
                return jsonify({'message': 'not handling groups'})

            # save message_id to prevent processing it again
            msg_id = d.get('id')
            logger.info(f'simulation message id -> {msg_id}')
            added = add_simulated_msg_id(msg_id)
            if not added:
                logger.info("Simulation Message not inserted. Probably it has been processed before")
                return jsonify({'message': 'not handling groups'})

        msisdn = from_.split('@')[0]
        kwargs = {'msisdn': msisdn, 'text': body, 'client_id': client_id, 'version': 1}
        if body.upper().startswith('REF') and ' ' not in body:
            q.enqueue(handle_referral_msg, args=(d, 1))
            # handle_referral_msg(d)
            return {'message': 'success'}
        if body.upper() in ['STOP', 'HI']:
            sn_id = str(datetime.now().timestamp())
            r.set(f'{client_id}:{msisdn}', sn_id)
            if body.upper() == 'STOP':
                return {'message': 'stopped'}
        _body = body.lower().split(" ")[0]
        if _body in ['/pay', 'pay', '.pay']:
            q.enqueue(handle_pay_prompt, kwargs=kwargs)
            # handle_pay_prompt(**kwargs)

        elif _body in ['/code']:
            q.enqueue(handle_getting_code, args=(d, 1))
        else:
            q.enqueue(handle_prompt, kwargs=kwargs, retry=Retry(max=4, interval=60))
    else:
        logger.warning("Method Not Allowed")
    return {'message': 'success'}


@app.route("/v2/messages", methods=["GET", "POST"])
def v2_messages_view():
    msg_payload = request.json
    if msg_payload.get('type') != 'message':
        return {'message': 'not a message'}
    logger.info("-----------------V2 MESSAGE---------------------------")
    logger.info(msg_payload)

    if msg_payload.get('body').get('key').get('fromMe'):
        logger.info("This is a self message. nothing to do")
        return {'message': 'not replying to own messages'}
    try:
        try:
            msg = msg_payload.get('body').get('message').get('extendedTextMessage').get('text')
        except Exception as x:
            logger.exception(x)
            msg = msg_payload.get('body').get('message').get('conversation')

        from_, server = msg_payload.get('body').get('key').get('remoteJid').split("@")
        data = {
            "from": from_,
            "body": msg,
            "ack": 1,
            "client_id": msg_payload.get('instanceKey'),
            "to": '',
            "sender": {
                "name": msg_payload.get('body').get('pushName'),
            }
        }

        kwargs = {'msisdn': data['from'], 'text': data.get('body'), 'client_id': data.get('client_id'), 'version': 2}
        body = data.get('body')
        client_id = data.get('client_id')
        msisdn = data.get('from')
        logger.info(f"REQUEST: {data}")

        if server == 'g.us':
            return {'message': 'not processing groups'}
            # if from_ not in os.environ.get('SUPPORT_GROUPS', '120363127313593286@g.us').split(','):
            #     return jsonify({'message': 'not handling groups'})
            # sim_values = [d for d in body.split(' ') if d]
            # sim_no = sim_values[0]
            # from_ = parse_msisdn(sim_no, log=False)
            # if not from_:
            #     return jsonify({'message': 'not handling groups'})
            # from_ += '@s.whatsapp.net'
            # body = ' '.join(sim_values[1:])
            #
            # # get client_id from the author of the message
            # author = msg_payload.get('body').get('key').get('participant').split("@")
            # client_id = r.hget(BOT_NUMBERS, author)
            # if not client_id:
            #     logger.error(f'No client id found for simulated message. author -> {author}')
            #     return jsonify({'message': 'not handling groups'})
            #
            # # save message_id to prevent processing it again
            # msg_id = d.get('id')
            # logger.info(f'simulation message id -> {msg_id}')
            # added = add_simulated_msg_id(msg_id)
            # if not added:
            #     logger.info("Simulation Message not inserted. Probably it has been processed before")
            #     return jsonify({'message': 'not handling groups'})

        if body.lower().startswith('.join') or body.lower().startswith('.stop'):
            q.enqueue(handle_lesson_subscription, args=(msisdn, data.get('sender').get('name'), body, client_id, 2))
            return {'message': 'success'}

        if body.upper().startswith('REF') and ' ' not in body:
            q.enqueue(handle_referral_msg, args=(data, 2))
            # handle_referral_msg(d)
            return {'message': 'success'}
        if body.upper() in ['STOP', 'HI']:
            sn_id = str(datetime.now().timestamp())
            r.set(f'{client_id}:{msisdn}', sn_id)
            if body.upper() == 'STOP':
                return {'message': 'stopped'}
        _body = body.lower().split(" ")[0]
        if _body in ['/pay', 'pay', '.pay', '"pay"', '"/pay"', "'pay'", "'/pay'"]:
            q.enqueue(handle_pay_prompt, kwargs=kwargs)
            #handle_pay_prompt(**kwargs)
            return {'message': 'success'}
        if _body in ['/code']:
            q.enqueue(handle_getting_code, args=(data, 2))
        else:
            q.enqueue(handle_prompt, kwargs=kwargs, retry=Retry(max=4, interval=60))
            # handle_prompt(**kwargs)
        return {'message': 'success'}
    except Exception as x:
        logger.exception(x)
        return {'error': str(x), 'error_class': f'{x.__class__}'}
