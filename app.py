import json
import logging
import os
from datetime import datetime, timedelta

import openai
from flask import Flask, request, jsonify
from rq import Queue

import crud
from constants import PAYMENT_RECEIVED_MESSAGE
from engine import r, handle_prompt
from helpers import send_notification, get_session_id, add_paid
from pgw import handle_pay_prompt
from schema import PaymentBase

logger = logging.getLogger(__name__)
app = Flask(__name__)
openai.api_key = os.getenv("OPENAI_API_KEY")
q = Queue('default', connection=r)


@app.route('/test', methods=['GET'])
def test():
    return {'message': 'success'}


@app.route('/payment', methods=['POST'])
def payment_view():
    req = request.json
    if isinstance(req, dict) and 'Body' in req and 'stkCallback' in req['Body']:

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

            expiry = datetime.now() + timedelta(days=30)
            add_paid(target, expiry)
            logger.info(f"Sending notification to {target} using {client_id}")
            send_notification(
                client_id,
                payment.msisdn,
                get_session_id(waiting.client_id, payment.msisdn),
                PAYMENT_RECEIVED_MESSAGE.format(
                    amount=payment.amount,
                    msisdn=payment.msisdn,
                    trx_id=payment.trx_id,
                    expiry=expiry.strftime("%d/%m/%Y, %H:%M")
                )
            )
        except Exception:
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
        from_ = d.get('from') or ''
        body = d.get('body')
        client_id = d.get('client_id')
        logger.info(f"request: from -> {from_}, body -> {body} -> client_id -> {client_id}")
        if not body or not from_:
            return jsonify({'error': 'Invalid Content'})

        if 'g.us' in from_:
            return jsonify({'message': 'not handling groups'})

        msisdn = from_.split('@')[0]
        kwargs = {'msisdn': msisdn, 'text': body, 'client_id': client_id}
        if body.upper() in ['STOP', 'HI']:
            sn_id = str(datetime.now().timestamp())
            r.set(f'{client_id}:{msisdn}', sn_id)
            if body.upper() == 'STOP':
                return {'message': 'stopped'}
        if body.lower().startswith('/pay'):
            # q.enqueue(handle_pay_prompt, kwargs=kwargs)
            handle_pay_prompt(**kwargs)
        else:
            q.enqueue(handle_prompt, kwargs=kwargs)
    return {'message': 'success'}
