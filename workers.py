#!/usr/bin/env python
import sys

from rq import Worker

# Preload libraries
# import library_that_you_want_preloaded

# Provide the worker with the list of queues (str) to listen to.
from constants import r

if __name__ == '__main__':
    try:
        queue_names = sys.argv[1:]
    except IndexError:
        raise Exception('You have not provided any queue names to listen to')

    if len(queue_names) < 1:
        raise Exception('You have not provided any queue names to listen to')

    w = Worker(queue_names, connection=r)
    w.work()
