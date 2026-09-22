"""Enqueue due research every 15 seconds independently of model execution."""
import logging
import time

from worker import connect
from scheduling import dispatch_due


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            with connect() as conn:
                queued = dispatch_due(conn)
            if queued:
                logging.info('Queued %s scheduled searches.', queued)
        except Exception as error:
            logging.error('Scheduler tick failed (%s); will retry.', type(error).__name__)
        time.sleep(15)
