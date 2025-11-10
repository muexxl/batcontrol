"""Scheduler Thread Module

This module provides a scheduler thread that runs alongside the main control loop.
It uses the schedule library to run periodic tasks at specific intervals.
"""

import datetime
import threading
import time
import logging
from unittest import case
import schedule
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class SchedulerThread:
    """Thread-based scheduler that runs periodic tasks using the schedule library"""

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False
        self._lock = threading.Lock()
        logger.info("Scheduler thread initialized")

    def start(self):
        """Start the scheduler thread"""
        with self._lock:
            if self._running:
                logger.warning("Scheduler thread is already running")
                return

            self._stop_event.clear()
            self._running = True
            self._thread = threading.Thread(target=self._run, daemon=True, name="SchedulerThread")
            self._thread.start()
            logger.info("Scheduler thread started")

    def stop(self):
        """Stop the scheduler thread"""
        with self._lock:
            if not self._running:
                logger.warning("Scheduler thread is not running")
                return

            logger.info("Stopping scheduler thread...")
            self._stop_event.set()
            self._running = False

        # Wait for thread to finish (with timeout)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
            if self._thread.is_alive():
                logger.warning("Scheduler thread did not stop gracefully")
            else:
                logger.info("Scheduler thread stopped")

    def _run(self):
        """Main loop for the scheduler thread"""
        logger.debug("Scheduler thread loop started")
        while not self._stop_event.is_set():
            try:
                logger.debug("Scheduler thread checking for pending jobs")
                schedule.run_pending()
                # Currently, we do not schedule any jobs dynamically here
                n = schedule.idle_seconds()
                if n is None:
                    n = 10  # Default sleep time if no jobs are scheduled
                if n > 0:
                    logger.debug("Scheduler thread sleeping for %d seconds until next job", n)
                    time.sleep(n)
            except Exception as e:
                logger.error("Error in scheduler thread: %s", e, exc_info=True)

        logger.debug("Scheduler thread loop ended")

    def is_running(self) -> bool:
        """Check if the scheduler thread is running"""
        return self._running

    def schedule_every(self, interval: int, unit: str, job: Callable, job_name: str = ""):
        """
        Schedule a job to run at regular intervals

        Args:
            interval: The interval value (e.g., 5 for "every 5 minutes")
            unit: The unit of time ('seconds', 'minutes', 'hours', 'days', 'weeks')
            job: The callable function to execute
            job_name: Optional name for the job (for logging purposes)

        Returns:
            The scheduled job object
        """
        name = job_name or job.__name__
        logger.info("Scheduling job '%s' to run every %d %s", name, interval, unit)

        # Create the scheduler based on the unit
        task = schedule.every(interval)

        if unit not in ['seconds', 'minutes', 'hours', 'days', 'weeks']:
            raise ValueError(f"Invalid unit '{unit}'. Must be one of: ['seconds', 'minutes', 'hours', 'days', 'weeks']")


        obtained_unit = task.__getattribute__(unit)

        # Wrap the job to catch exceptions and add logging
        def wrapped_job():
            try:
                logger.info("Running scheduled job: %s", name)
                job()
                logger.info("Completed scheduled job: %s", name)
            except Exception as e:
                logger.error("Error in scheduled job '%s': %s", name, e, exc_info=True)

        wrapped_job.__name__ = name
        x = obtained_unit.do(wrapped_job)
        return x

    def schedule_at(self, time_str: str, job: Callable, job_name: str = ""):
        """
        Schedule a job to run at a specific time each day

        Args:
            time_str: Time string in HH:MM format (e.g., "14:30")
            job: The callable function to execute
            job_name: Optional name for the job (for logging purposes)

        Returns:
            The scheduled job object
        """
        name = job_name or job.__name__
        logger.info("Scheduling job '%s' to run daily at %s", name, time_str)

        # Wrap the job to catch exceptions and add logging
        def wrapped_job():
            try:
                logger.debug("Running scheduled job: %s", name)
                job()
                logger.debug("Completed scheduled job: %s", name)
            except Exception as e:
                logger.error("Error in scheduled job '%s': %s", name, e, exc_info=True)

        return schedule.every().day.at(time_str).do(wrapped_job)

    def schedule_once(self, time: str, job: Callable, job_name: str = ""):
        """
        Schedule a job to run once at a specific date and time

        Args:
            time: The date and time to run the job
            job: The callable function to execute
            job_name: Optional name for the job (for logging purposes)

        Returns:
            The scheduled job object
        """
        name = job_name or job.__name__
        logger.info("Scheduling job '%s' to run once at %s", name, time)

        # Wrap the job to catch exceptions and add logging
        def wrapped_job():
            try:
                logger.info("Running scheduled one-time job: %s", name)
                job()
                logger.info("Completed scheduled one-time job: %s", name)
                return schedule.CancelJob
            except Exception as e:
                logger.error("Error in scheduled one-time job '%s': %s", name, e, exc_info=True)

        return schedule.every().day.at(time).do(wrapped_job).tag(f"one_time_{name}")

    def clear_jobs(self):
        """Clear all scheduled jobs"""
        logger.info("Clearing all scheduled jobs")
        schedule.clear()

    def get_jobs(self):
        """Get all currently scheduled jobs"""
        return schedule.get_jobs()
