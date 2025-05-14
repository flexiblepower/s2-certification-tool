import logging
import logging.config
from typing import Dict


def get_log_config(test_log_file_name=None) -> Dict:
    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "()": "logging.Formatter",
                "fmt": "%(asctime)s - %(name)s:%(lineno)d - %(levelname)s - %(message)s",
            },
            "log-file": {
                "()": "logging.Formatter",
                "fmt": "%(message)s",
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
            "connectivity": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False,
            },
            "ws_adapter": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False,
            },
            "websockets": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": True,
            },
            "asyncio": {"handlers": ["console"], "level": "WARNING", "propagate": True},
            "test-suite-logger": {
                "handlers": ["console"],
                "level": "DEBUG",
                "propagate": False,
            },
        },
    }

    if test_log_file_name is not None:
        config["handlers"] = {
            **config["handlers"],
            "test-suite-log-handler": {
                "class": "logging.FileHandler",
                "formatter": "log-file",
                "filename": test_log_file_name,
                # "filename": "test_suite.log",
                "mode": "w",
            },
        }
        config["loggers"] = {
            **config["loggers"],
            "test-suite-logger": {
                "handlers": ["test-suite-log-handler", "console"],
                "level": "DEBUG",
                "propagate": False,
            },
        }

    return config
