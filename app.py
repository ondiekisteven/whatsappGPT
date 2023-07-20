import json
import logging
import os
from datetime import datetime, timedelta

import openai
import requests
from flask import Flask, request, jsonify
from rq import Queue, Retry

import crud
from constants import PAYMENT_RECEIVED_MESSAGE, BOT_NUMBERS
from engine import r, handle_prompt
from helpers import send_notification, get_session_id, add_paid, parse_msisdn, add_simulated_msg_id, update_clients, \
    handle_referral_msg, handle_getting_code
from pgw import handle_pay_prompt
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
                client_id,
                reply_to,
                get_session_id(client_id, error_msisdn),
                f'*An Error Occurred When Processing Your Payment:*: \n\n\n{error_desc}'
            )
            if reply_to != error_msisdn:
                send_notification(
                    client_id,
                    error_msisdn,
                    get_session_id(client_id, error_msisdn),
                    f'*An Error Occurred When Processing Your Payment:*: \n\n\n{error_desc}'
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
            else:
                logger.warning("Payment has no matching waiting record. Using Default Client ID")
                client_id = os.getenv('DEFAULT_CLIENT_ID')
                target = payment.msisdn

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
            from_ = parse_msisdn(sim_no, log=False)
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
        kwargs = {'msisdn': msisdn, 'text': body, 'client_id': client_id}
        if body.upper().startswith('REF') and ' ' not in body:
            q.enqueue(handle_referral_msg, args=(d,))
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
            q.enqueue(handle_getting_code, args=(d,))
        else:
            q.enqueue(handle_prompt, kwargs=kwargs, retry=Retry(max=4, interval=60))
    else:
        logger.warning("Method Not Allowed")
    return {'message': 'success'}


@app.route("/v2/messages", methods=["GET", "POST"])
def v2_messages_view():
    msg_payload = request.json
    logger.info("-----------------V2 MESSAGE---------------------------")
    logger.info(msg_payload)
    try:
        data = {
            "from": msg_payload.get('body').get('key').get('remoteJid').split("@")[0],
            "body": msg_payload.get('body').get('message').get('conversation'),

            "ack": 1,
            "client_id": msg_payload.get('instanceKey'),
            "to": '',
            "sender": {
                "name": msg_payload.get('body').get('pushName'),
            }
        }
        kwargs = {'msisdn': data['from'], 'text': data.get('body'), 'client_id': data.get('client_id')}
        body = data.get('body')
        client_id = data.get('client_id')
        msisdn = data.get('from')

        if body.upper().startswith('REF') and ' ' not in body:
            q.enqueue(handle_referral_msg, args=(d,))
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
            q.enqueue(handle_getting_code, args=(data,))
        else:
            q.enqueue(handle_prompt, kwargs=kwargs, retry=Retry(max=4, interval=60))
        return {'message': 'success'}
    except Exception as x:
        logger.exception(x)
        return {'error': str(x)}
