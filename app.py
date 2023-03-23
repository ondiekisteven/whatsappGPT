import os

import openai
from flask import Flask, redirect, render_template, request, url_for, jsonify
from rq import Queue

from engine import r, handle_prompt

app = Flask(__name__)
openai.api_key = os.getenv("OPENAI_API_KEY")
q = Queue('default', connection=r)


@app.route("/", methods=("GET", "POST"))
def index():
    if request.method == "POST":
        d = request.json
        from_ = d.get('from') or ''
        body = d.get('body')
        if not body or not from_:
            return jsonify({'error': 'Invalid Content'})

        if 'g.us' in from_:
            return jsonify({'message': 'not handling groups'})

        msisdn = from_.split('@')[0]
        q.enqueue(handle_prompt, kwargs={'msisdn': msisdn, 'text': body, 'client_id': d.get('client_id')})
    return {'message': 'success'}
