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

DEPLETED_CREDITS_MESSAGE = """*Your free credits have been depleted for today*, but don't worry... 

With just Ksh. {upgrade_amount}, you can use the bot *For A Whole Month*, and do your research and assignments

*REPLY WITH THIS MESSAGE TO PAY👇*:  

/pay 


or */pay 07xxxxxxxxxx* to pay using a different number. Remember to enter the phone number 

Upgrade now to support our work, and keep using the bot uninterrupted

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

# REDIS OBJECT NAMES
NOT_PAID = 'NOT_PAID'
PAID = 'PAID'
DEPLETED = 'DEPLETED_AND_NOTIFIED'
EXPIRED_NOTIFIED = 'TRIAL_EXPIRED_AND_NOTIFIED'
SUBSCRIPTION_EXPIRED_NOTIFIED = 'SUBSCRIPTION_EXPIRED_AND_NOTIFIED'

BOT_CLIENTS = 'BOT_CLIENTS'
BOT_NUMBERS = 'BOT_NUMBERS'
USERS = 'ALL_USERS'
REFERRAL_CODES = 'USED_REFERRAL_CODES'

EXPIRED = 'EXPIRED_USERS'
SIMULATED = 'SIMULATED_MESSAGE_IDS'

UPGRADE_AMOUNT = int(os.getenv('UPGRADE_AMOUNT', 50))
FREE_RESPONSES = int(os.getenv('FREE_RESPONSES', 10))
FREE_TRIAL = int(os.getenv('FREE_TRIAL_PERIOD', 7))

TRIAL_PERIOD_OVER = f"""
*Your trial period on Sonia bot is over*. 

Pay Ksh. {UPGRADE_AMOUNT} to continue using the bot for the next one month

Send the word "/pay" to pay

For any questions, reach out to support at 254790670635
"""

RENEW_SUBSCRIPTION_MESSAGE = f"""
*Your subscription to Sonia Bot has expired. Kindly renew by sending the message "/pay". 

Pay Ksh. {UPGRADE_AMOUNT} to continue using the bot for the next one month

Thanks for being a valued user of Sonia Bot
For queries, please contact 254790670635
"""

# openai.api_key = os.getenv("OPENAI_API_KEY")
r_host = os.getenv('REDIS_HOST', 'localhost')
r = Redis(host=r_host, db=os.getenv('REDIS_DB', 5), charset="utf-8", decode_responses=True)

high = Queue('high', connection=r)
default = Queue('default', connection=r)
