import logging
import logging.handlers
import os
from pathlib import Path


def setup_logging(log_dir: str = "logs", log_file: str = "bot.log") -> logging.Logger:
    """
    Configure logging with both file and console handlers.

    Args:
        log_dir: Directory to store log files
        log_file: Name of the log file
    """
    # Create logs directory if it doesn't exist
    Path(log_dir).mkdir(exist_ok=True)

    # Create logger
    logger = logging.getLogger("fpvgate-bot")
    logger.setLevel(logging.DEBUG)  # Capture all levels

    # Create formatters
    file_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_formatter = logging.Formatter(
        "[%(levelname)-8s] %(name)s: %(message)s"
    )

    # File handler - writes all logs to file
    file_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, log_file),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,  # Keep 5 old files
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Console handler - writes INFO and above to console
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # Set discord.py logging to INFO to avoid spam
    logging.getLogger("discord").setLevel(logging.INFO)
    logging.getLogger("discord.http").setLevel(logging.WARNING)

    return logger
