import logging
import logging.config
from typing import Dict

LOGGING_CONFIG: Dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "()": "logging.Formatter",
            "fmt": "%(asctime)s - %(name)s:%(lineno)d - %(levelname)s - %(message)s",
        },
        "short": {
            "()": "logging.Formatter",
            "fmt": "%(name)s:%(lineno)d - %(levelname)s - %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "short",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        "": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
        "connectivity": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "ws_adapter": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "websockets": {"handlers": ["console"], "level": "WARNING", "propagate": True},
        "asyncio": {"handlers": ["console"], "level": "WARNING", "propagate": True},
    },
}
