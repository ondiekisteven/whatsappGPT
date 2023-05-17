from datetime import timedelta, datetime

from constants import logger
from crud import get_last_payment, get_payments
from helpers import add_paid


def reconcile_payments(msisdn):
    last_payment = get_last_payment(msisdn)
    logger.info(f"Last payment for {msisdn} -> {last_payment}")
    if last_payment:
        date_paid = last_payment.date_created
        expiry = date_paid + timedelta(days=30)
        if expiry > datetime.now():
            logger.info(f"User has not expired. Expiry -> {expiry}")
            add_paid(msisdn, expiry)
            logger.info(f"Done reconciling user: msisdn -> {msisdn}")
        else:
            logger.warning(f"User payment has expired. Msisdn -> {msisdn} Expiry: -> {expiry}")
    else:
        logger.warning(f"No Last Payment found for user msisdn -> {msisdn}")


def main():
    payments = get_payments()
    logger.info(f'Fetched {len(payments)} payments')
    for payment in payments:
        logger.info(f"Reconciling payment object: {payment}")
        msisdn = payment.msisdn
        reconcile_payments(msisdn)


if __name__ == '__main__':
    main()
