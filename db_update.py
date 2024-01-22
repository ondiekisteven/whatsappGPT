import cfg_load

from db import *

configs = cfg_load.load('config.yaml')
engine = create_db(configs['database'])
metadata.create_all(engine, [
    MalawiFlutterPaymentsWaiting.__table__, MalawiFlutterPayments.__table__, TanzaniaPaymentsWaiting.__table__])
