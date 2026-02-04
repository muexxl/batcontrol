"""
Custom exceptions for inverter module.

These exceptions provide specific error handling for inverter-related failures,
particularly for handling temporary outages gracefully.
"""


class InverterOutageError(Exception):
    """
    Exception raised when an inverter has been unreachable for too long.

    This exception is raised after the configured outage tolerance period
    (default: 24 minutes) has elapsed without successful communication
    with the inverter. This allows batcontrol to distinguish between:

    1. Configuration errors (fail immediately on first run)
    2. Transient outages (tolerate for up to 24 minutes using cached values)
    3. Permanent outages (terminate after 24 minutes)

    Attributes:
        message: Explanation of the error
        outage_duration_seconds: How long the inverter has been unreachable
    """

    def __init__(self, message: str, outage_duration_seconds: float = 0):
        super().__init__(message)
        self.message = message
        self.outage_duration_seconds = outage_duration_seconds

    def __str__(self):
        minutes = self.outage_duration_seconds / 60
        return f"{self.message} (outage duration: {minutes:.1f} minutes)"


class InverterCommunicationError(Exception):
    """
    Exception raised when communication with the inverter fails.

    This is a general exception for inverter communication failures that
    can be caught and handled by the resilient wrapper to provide
    cached values during temporary outages.
    """

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message
