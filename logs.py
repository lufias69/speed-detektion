import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logging(log_path: str) -> logging.Logger:
    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
    logger = logging.getLogger("speedmonitor")
    logger.setLevel(logging.INFO)

    # Check handlers attached to *this* logger only; hasHandlers() propagates to
    # ancestor loggers (e.g. root) and would wrongly skip attaching here.
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
