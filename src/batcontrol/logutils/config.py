import logging
import sys
import os

def setup_logging(level=logging.INFO, logfile=None) -> logging.Logger:
    """Configure root logger with consistent formatting."""
    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Clear existing handlers to avoid duplicates
    root_logger.handlers = []
    
    # Create formatter with module name included
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        "%Y-%m-%d %H:%M:%S"
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler if specified
    if logfile:
        if not os.path.exists(os.path.dirname(logfile)):
            os.makedirs(os.path.dirname(logfile))
        file_handler = logging.FileHandler(logfile)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
        
    return root_logger