from .core import Batcontrol
import time
import datetime
import sys
import logging


CONFIGFILE = "config/batcontrol_config.yaml"
EVALUATIONS_EVERY_MINUTES = 3  # Every x minutes on the clock

def main() -> int:
    loglevel = logging.DEBUG
    logger = logging.getLogger(__name__)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s",
                              "%Y-%m-%d %H:%M:%S")

    bc = Batcontrol(CONFIGFILE)
    try:
        while True:
            bc.run()
            loop_now = datetime.datetime.now().astimezone(bc.timezone)
            # reset base to full minutes on the clock
            next_eval = loop_now - datetime.timedelta(
                minutes=loop_now.minute % EVALUATIONS_EVERY_MINUTES,
                seconds=loop_now.second,
                microseconds=loop_now.microsecond
            )
            # add time increments to trigger next evaluation
            next_eval += datetime.timedelta(minutes=EVALUATIONS_EVERY_MINUTES)
            sleeptime = (next_eval - loop_now).total_seconds()
            logger.info("Next evaluation at %s. Sleeping for %d seconds", next_eval.strftime('%H:%M:%S'), int(sleeptime))
            time.sleep(sleeptime)
    except KeyboardInterrupt:
        print("Shutting down")
    finally:
        bc.shutdown()
        del bc
    return 0

if __name__ == "__main__":
    sys.exit(main())