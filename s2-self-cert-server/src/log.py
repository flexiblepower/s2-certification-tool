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
        "watchfiles.main": {"handlers": ["console"], "level": "WARNING", "propagate": True},
        "websockets": {"handlers": ["console"], "level": "WARNING", "propagate": True},
        "asyncio": {"handlers": ["console"], "level": "WARNING", "propagate": True},
    },
}
