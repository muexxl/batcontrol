"""
Scheduler Examples

This file demonstrates how to use the scheduler module with both the global functions
and the SchedulerThread class.

The scheduler module provides two ways to schedule jobs:

1. Global functions (recommended for most cases):
   - schedule_every() - Schedule recurring jobs
   - schedule_at() - Schedule daily jobs at specific times
   - schedule_once() - Schedule one-time jobs
   - clear_jobs() - Clear all scheduled jobs
   - get_jobs() - Get list of all scheduled jobs

2. SchedulerThread instance methods (for backward compatibility):
   - Same methods as above, but called on a SchedulerThread instance

The global functions are recommended because they can be called from any context
without needing a SchedulerThread instance.
"""

import logging
from .scheduler import schedule_every, schedule_at, schedule_once, SchedulerThread

logger = logging.getLogger(__name__)


# Example 1: Using global functions (recommended)
def example_global_scheduling():
    """Example of using global scheduler functions"""
    
    def my_task():
        logger.info("Task executed!")
    
    # Schedule a task to run every 5 minutes
    schedule_every(5, 'minutes', my_task, 'my-recurring-task')
    
    # Schedule a task to run daily at 14:30
    schedule_at('14:30', my_task, 'my-daily-task')
    
    # Schedule a task to run once at 15:00
    schedule_once('15:00', my_task, 'my-one-time-task')


# Example 2: Using global functions from another module
def example_from_another_module():
    """
    This example shows how you can import and use the scheduler functions
    from any other module in your application without needing a SchedulerThread instance.
    """
    from batcontrol.scheduler import schedule_every
    
    def refresh_data():
        logger.info("Refreshing data...")
    
    # This can be called from anywhere in your application
    schedule_every(10, 'minutes', refresh_data, 'data-refresh')


# Example 3: Using SchedulerThread instance (backward compatible)
def example_scheduler_thread():
    """Example of using SchedulerThread instance methods (backward compatible)"""
    
    # Create and start the scheduler thread
    scheduler = SchedulerThread()
    scheduler.start()
    
    def my_task():
        logger.info("Task executed!")
    
    # These methods delegate to the global functions internally
    scheduler.schedule_every(5, 'minutes', my_task, 'my-task')
    scheduler.schedule_at('14:30', my_task, 'daily-task')
    
    # The scheduler thread will keep running and executing scheduled jobs
    # until you call scheduler.stop()


# Example 4: Complete usage with error handling
def example_complete():
    """Complete example with error handling"""
    from batcontrol.scheduler import schedule_every, get_jobs, clear_jobs
    
    def critical_task():
        logger.info("Critical task running")
        # Your task logic here
    
    # Schedule the task
    job = schedule_every(1, 'hours', critical_task, 'critical-hourly-task')
    
    # Check what jobs are scheduled
    jobs = get_jobs()
    logger.info(f"Currently scheduled jobs: {len(jobs)}")
    
    # Later, if you need to clear all jobs
    # clear_jobs()
