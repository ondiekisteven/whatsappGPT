import logging.config
import os
from collections import namedtuple

import cfg_load
from redis.client import Redis
from rq import Queue

from db import create_db

config_path = os.getenv('CONFIG_FILE', 'config.yaml')
try:
    confg = cfg_load.load(config_path)
except FileNotFoundError:
    raise NotImplementedError(
        "You have not specified a config file path. Default config name is 'config.yaml'")

LOGGING_CONFIG = None
LOGLEVEL = os.getenv('LOGGING_LEVEL', 'info').upper()
BASE_DIR = os.path.dirname(__file__)

if not os.path.exists(os.path.join(BASE_DIR, 'logs')):
    os.mkdir(os.path.join(BASE_DIR, 'logs'))

logging.config.dictConfig({
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'console': {
            "format": "%(asctime)s\t%(levelname)s\t%(filename)s\t%(message)s"
        },
        "standard": {
            "class": "logging.Formatter",
            'format': '%(asctime)s %(levelname)s [%(name)s:%(lineno)s] %(message)s',
            "datefmt": "%d %b %y %H:%M:%S"
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'console',
            "level": "INFO",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "standard",
            "level": "INFO",
            "filename": os.path.join(BASE_DIR, 'logs/chatgpt.log'),
            "mode": "a",
            "encoding": "utf-8",
            "maxBytes": 5000000,
            "backupCount": 20
        }
    },

    'loggers': {
        '': {
            'level': LOGLEVEL,
            'handlers': ['file', 'console'],
        },
    },
})

logger = logging.getLogger('engine')

engine = create_db(confg['database'])

DEPLETED_CREDITS_MESSAGE = """*Your free credits have been depleted for today*, but don't worry... 

With just {symbol}. {upgrade_amount}, you can use the bot *For A Whole Month*, and do your research and assignments

*REPLY WITH THIS MESSAGE TO PAY👇*:  

/pay 


Upgrade now to support our work, and keep using the bot uninterrupted

*You will get free credits tomorrow. Don't forget to come back*


Thanks for using Sonia AI
"""

STK_PUSH_SENT_MESSAGE = """
We have sent an stk push to the number: {phone_number} Kindly enter your mpesa pin to complete the transaction

Thanks for using Sonia AI
"""

MALAWI_PAYMENT_REQUESTED_MESSAGE = """
Send MWK {upgrade_amount} to this phone number: {receiving_number} ({receiving_name}).

Once you have sent, wait for a few minutes for the payments to reflect on the system and you will get access to the bot.
We will send you a notification once the payment has been verified.

Thank you for using Sonia AI
"""

MALAWI_PAYMENT_RECEIVED_MESSAGE = \
    """We have successfully received a payment of MWK. {amount} from {msisdn}, with transaction id {trx_id}. 
    
    You have now received unlimited access to the bot for the next one month. Your subscription expires on {expiry}
    
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

PREMIUM_USERS = 'PREMIUM_USERS'

KENYA_UPGRADE_AMOUNT = int(os.getenv('KENYA_UPGRADE_AMOUNT', 100))
TANZANIA_UPGRADE_AMOUNT = int(os.getenv('TANZANIA_UPGRADE_AMOUNT', 250))
MALAWI_UPGRADE_AMOUNT = int(os.getenv('MALAWI_UPGRADE_AMOUNT', 1000))
FREE_RESPONSES = int(os.getenv('FREE_RESPONSES', 10))
FREE_TRIAL = int(os.getenv('FREE_TRIAL_PERIOD', 7))

TRIAL_PERIOD_OVER = """
*Your trial period on Sonia bot is over*. 

Pay {symbol}. {upgrade_amount} to continue using the bot for the next one month

Send the word "/pay" to pay

For any questions, reach out to support at 254790670635
"""

RENEW_SUBSCRIPTION_MESSAGE = """
*Your subscription to Sonia Bot has expired. Kindly renew by sending the message "/pay". 

Pay {symbol}. {upgrade_amount} to continue using the bot for the next one month

Thanks for being a valued user of Sonia Bot
For queries, please contact 254790670635
"""

REFERRAL_CODE_NOT_FOUND_MESSAGE = """*Invalid Referral Code*. The referral code you sent does not exist. 
Check again and make sure you copy the right referral code. 

For queries, please contact 254790670635
"""

USER_HAS_ANOTHER_INVITE_MESSAGE = """*Error processing referral code*. You were already invited by another user. 
You cannot use more than one invite code 

For queries, please contact 254790670635
"""

USER_MORE_THAN_2_DAYS_MESSAGE = """*Error processing referral code*. 
You have used the bot for more than 2 days, you cannot add a referral code now.

For queries, please contact 254790670635
"""

UPLINE_ADDED_MESSAGE = """Welcome To Sonia AI. You have been invited by {referer_msisdn}. You will now been given {
credits_count} free credits to use daily for {free_trial} days.

To find out what I can do, type /help. 

You can also ask me any questions, I will answer them instantly."""

DOWNLINE_ADDED_MESSAGE = """New user added with your referral code.

Phone Number: {downline_msisdn}.

You have now a total of {downlines_count} referred users. 
Thanks for helping Sonia AI to grow. 
"""

ERROR_GENERATING_RESPONSE = """
An error occurred when generating a response. We apologize for that. Please try your question again after a few minutes.

Thank you for using Sonia AI 
"""

LESSON_SUBSCRIBED = """Greetings {name}, You have successfully subscribed to Pipeline Lesson Forum. 
You will be receiving a summary of each day's lesson at 5:00 a.m daily. 

The summary is just to help you know the main points talked about in the lesson for the day. 
Please take your time to study the lesson and refer to the bible for a deeper understanding.

Happy Studying🙏

To unsubscribe from the program, send this message👇: 

.stop lesson
"""

LESSON_UNSUBSCRIBED = """Greetings {name}, You have been unsubscribed from Pipeline Lesson Forum and will not be 
receiving the daily lesson summary 

It is sad to see you leave.

If there is anything we can do to make your experience better, we would appreciate your feedback. 
You can send your feedback or suggestion to this number: +254790670635
 
To join the program again, send this message👇:

.join lesson

👋
-_Sonia AI_
"""
LESSON_ACTION_ERROR = """An error occurred when processing your request.
Kindly try sending your message again after a few minutes. 

If the error persists, report the issue to +254790670635

Thank you for using Sonia AI
"""


# openai.api_key = os.getenv("OPENAI_API_KEY")
r_host = os.getenv('REDIS_HOST', 'localhost')
r = Redis(
    host=r_host,
    password=os.getenv('REDIS_PASSWORD'),
    db=int(os.getenv('REDIS_DB', 5)),
    charset="utf-8",
)

high = Queue('high', connection=r)
default = Queue('default', connection=r)
adverts_queue = Queue('adverts', connection=r)

currency_obj = namedtuple('currency_obj', ('symbol', 'amount'))
phones_mapping = {
    '9': ('265992641392', 'Dolika Nkhoma'),
    '8': ('265884749249', 'Clara Banda'),
}

SECONDS_BEFORE_ADVERT = int(os.getenv('SECONDS_BEFORE_ADVERT', '10'))
