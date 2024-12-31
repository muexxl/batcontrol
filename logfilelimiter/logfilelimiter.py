#! /usr/bin/env python
"""
This module provides a LogFileLimiter class that limits the size of a log file by
deleting the oldest lines.

Classes:
    LogFileLimiter: A class that limits the size of a log file by deleting the
    oldest lines.

"""
import os
import logging
logger = logging.getLogger('__main__')
logger.info('[LogFileLimiter] loading module')


class LogFileLimiter:
    """ A class that limits the size of a log file by deleting the oldest lines. """
    def __init__(self, path, max_size):
        """
        Initialize the LogFileLimiter class with the path to the file and
        the maximum size in kilobytes.

        :param path: Path to the log file.
        :param max_size: Maximum file size in kilobytes.
        """
        self.path = path
        self.max_size = max_size * 1024  # Convert kilobytes to bytes

    def prune(self, prune_factor):
        """
        Reduces the file size by deleting the earliest lines.
        :param prune_factor: The fraction of total lines to delete.
        """
        if prune_factor < 0 or prune_factor > 1:
            raise ValueError("Prune factor must be between 0 and 1.")

        logger.info(
            '[LogFileLimiter] File %s is too large. File will be pruned by %.2f %%',
            self.path,
            prune_factor * 100
        )
        with open(self.path, 'r+', encoding='UTF-8') as file:
            lines = file.readlines()
            file.seek(0)
            file.truncate()
            file.writelines(lines[int(len(lines) * prune_factor):])

    def run(self):
        """
        Checks the file size and calls the prune method if necessary.
        """
        file_size = os.path.getsize(self.path)
        if file_size > self.max_size:
            # Determine the prune factor, at least 10%
            prune_factor = max(0.1, 1 - self.max_size / file_size)
            self.prune(prune_factor)

# Example usage
if __name__ == "__main__":
    limiter = LogFileLimiter("test copy.log", 20)  # Maximum size of 20 KB
    limiter.run()
