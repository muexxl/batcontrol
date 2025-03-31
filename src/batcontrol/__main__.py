from .core import Batcontrol
from .setup import setup_logging, load_config
import time
import datetime
import sys
import logging


CONFIGFILE = "config/batcontrol_config.yaml"
EVALUATIONS_EVERY_MINUTES = 3  # Every x minutes on the clock
LOGFILE_ENABLED_DEFAULT = True
LOGFILE = "logs/batcontrol.log"

def main() -> int:
    # Configure a basic logger to be able to log even before the configuration is loaded
    setup_logging(level=logging.INFO)
    logger = logging.getLogger(__name__)
    logger.info('Starting Batcontrol')

    # Load the configuration
    config = load_config(CONFIGFILE, LOGFILE_ENABLED_DEFAULT)

    # Load the config for the logger with the loaded configuration
    loglevel = config.get('loglevel', 'info')
    logfile_enabled = config.get('logfile_enabled', LOGFILE_ENABLED_DEFAULT)
    logfile = LOGFILE if logfile_enabled else None

    if not logfile_enabled:
        logger.info("Logfile disabled in config. Proceeding without logfile")

    # Establish the loglevel mapping
    loglevel_mapping = {
        'debug': logging.DEBUG,
        'warning': logging.WARNING,
        'error': logging.ERROR,
        'info': logging.INFO
    }

    # Setup the logger based on the config
    setup_logging(level=loglevel_mapping.get(loglevel, logging.INFO), logfile=logfile)
    logger = logging.getLogger(__name__)

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