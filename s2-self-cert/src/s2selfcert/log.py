import datetime
import json
import logging
import logging.config
from typing import Dict


class JsonFormatter(logging.Formatter):
    def format(self, record):
        # log_record = {
        #     "timestamp": datetime.datetime.fromtimestamp(record.created).isoformat(),
        #     "level": record.levelname,
        #     "message": record.getMessage(),
        #     "s2_message": record.__dict__["s2_message"],
        #     "sender": record.__dict__["sender"],
        #     "receiver": record.__dict__["receiver"],
        # }

        s2_message = record.__dict__["s2_message"]
        sender = record.__dict__["sender"]
        receiver = record.__dict__["receiver"]

        message = f"{record.levelname}: {sender} -> {receiver} ({s2_message['message_type']})\n{json.dumps(s2_message, indent=2, default=str)}"

        return message
        # return json.dumps(log_record, default=str)


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
            "message-logger": {
                "()": "s2selfcert.log.JsonFormatter",
                "fmt": "%(asctime)s [MESSAGE LOGGER] %(message)s",
            },
            "plain": {
                "()": "logging.Formatter",
                "fmt": "%(message)s",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "short",
                "stream": "ext://sys.stdout",
            },
            "messages-handler": {
                "class": "logging.StreamHandler",
                "formatter": "message-logger",
                "stream": "ext://sys.stdout",
            },
            "messages-file-handler": {
                "class": "logging.FileHandler",
                "formatter": "message-logger",
                "filename": "messages.log",
                "mode": "w",
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
                "level": "DEBUG",
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
            "messages": {
                "handlers": ["messages-file-handler"],
                "level": "INFO",
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
