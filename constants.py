import os
import logging.config

import cfg_load
from redis.client import Redis
from rq import Queue

from db import create_db
from wp import Whatsapp

wa = Whatsapp(os.getenv('API_USERNAME'), os.getenv('API_PASSWORD'))
config_path = os.getenv('CONFIG_FILE', 'config.yaml')
try:
    confg = cfg_load.load(config_path)
except FileNotFoundError:
    raise NotImplementedError(
        "You have not specified a config file path. Default config name is 'config.yaml'")

logging.config.fileConfig('logging.conf', disable_existing_loggers=False)

logger = logging.getLogger('engine')
engine = create_db(confg['database'])

DEPLETED_CREDITS_MESSAGE = """
*Your free credits have been depleted for today*. 

In order to continue using the bot, you can upgrade to unlimited credits for a whole month by making a payment of Ksh. {upgrade_amount}. 
*REPLY WITH THIS MESSAGE TO PAY👇*:  

/pay 


*If you wish to pay using a different number other than {default_number}, send this message*

/pay phone_number

For example to pay using 0712345678, send this: 

/pay 0712345678

*You will get free credits tomorrow. Don't forget to come back*


Thanks for using Sonia AI
"""
STK_PUSH_SENT_MESSAGE = """
We have sent an stk push to the number: {phone_number} Kindly enter your mpesa pin to complete the transaction

Thanks for using Sonia AI
"""

PAYMENT_RECEIVED_MESSAGE = """
We have successfully received a payment of Ksh. {amount} from {msisdn}, with transaction id {trx_id}. 

You have now received unlimited access to the bot for the next one month. Your subscription expires on {expiry}

Thanks for using Sonia AI
"""


NOT_PAID = 'NOT_PAID'
PAID = 'PAID'
DEPLETED = 'DEPLETED_AND_NOTIFIED'

UPGRADE_AMOUNT = int(os.getenv('UPGRADE_AMOUNT', 50))
FREE_RESPONSES = int(os.getenv('FREE_RESPONSES', 10))

# openai.api_key = os.getenv("OPENAI_API_KEY")
r_host = os.getenv('REDIS_HOST', 'localhost')
r = Redis(host=r_host, db=os.getenv('REDIS_DB', 5), charset="utf-8", decode_responses=True)

high = Queue('high', connection=r)
