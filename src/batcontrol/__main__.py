from .core import Batcontrol
import time
import datetime
import sys

CONFIGFILE = "config/batcontrol_config.yaml"
LOGFILE = "logs/batcontrol.log"
EVALUATIONS_EVERY_MINUTES = 3  # Every x minutes on the clock

def main() -> int:
    bc = Batcontrol(CONFIGFILE, LOGFILE)
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
            print(f"Next evaluation at {next_eval.strftime('%H:%M:%S')}. Sleeping for {sleeptime:.0f} seconds")
            time.sleep(sleeptime)
    except KeyboardInterrupt:
        print("Shutting down")
    finally:
        bc.shutdown()
        del bc
    return 0

if __name__ == "__main__":
    sys.exit(main())