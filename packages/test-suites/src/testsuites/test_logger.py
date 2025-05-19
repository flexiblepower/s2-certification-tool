import logging
import abc
import asyncio
from enum import Enum
import logging
from typing import Callable, Literal, Optional

from pydantic import BaseModel

from testsuites.envelope_models import LogMessage, LogMessageEnvelope
from testsuites.certificate.certificate import (
    TestResultStatus,
)
from connectivity.channel import Channel


logger = logging.getLogger(__name__)


class TestLoggerLevel(str, Enum):
    SUCCESS = "SUCCESS"
    SOFT_ERROR = "SOFT_ERROR"
    ERROR = "ERROR"
    INFO = "INFO"
    DEBUG = "DEBUG"


RESULT_STATUS_TO_LOG_LEVEL = {
    TestResultStatus.PASS: TestLoggerLevel.SUCCESS,
    TestResultStatus.FAIL: TestLoggerLevel.ERROR,
    TestResultStatus.SOFT_FAIL: TestLoggerLevel.SOFT_ERROR,
    TestResultStatus.N_A: TestLoggerLevel.INFO,
}


class AbstractTestLogger(abc.ABC):

    def info(self, message, ident=2):
        logger.info("%s[INFO] %s", message)

    def success(self, message, ident=2):
        logger.info("%s[SUCCESS] %s", message)

    def soft_error(self, message, ident=2):
        logger.warning("%s[SOFT-FAIL] %s", message)

    def error(self, message, ident=2):
        logger.warning("%s[FAIL] %s", message)

    @abc.abstractmethod
    def log(self, message, level: TestLoggerLevel = TestLoggerLevel.INFO, ident=2):
        pass

    def log_status_list(self, message, statuses: list[TestResultStatus], ident=2):
        if TestResultStatus.FAIL in statuses:
            self.error(message, ident=ident)
        elif TestResultStatus.SOFT_FAIL in statuses:
            self.soft_error(message, ident=ident)
        elif TestResultStatus.PASS in statuses:
            self.success(message, ident=ident)


class TestLogger(AbstractTestLogger):

    logger: logging.Logger

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def info(self, message, ident=2):
        self.logger.info("%s[INFO] %s", " " * ident, message)

    def success(self, message, ident=2):
        self.logger.info("%s[SUCCESS] %s", " " * ident, message)

    def soft_error(self, message, ident=2):
        self.logger.warning("%s[SOFT-FAIL] %s", " " * ident, message)

    def error(self, message, ident=2):
        self.logger.warning("%s[FAIL] %s", " " * ident, message)

    def level_to_function(self, level) -> Callable[[str, int], None]:
        return {
            TestLoggerLevel.SUCCESS: self.success,
            TestLoggerLevel.ERROR: self.error,
            TestLoggerLevel.SOFT_ERROR: self.soft_error,
            TestLoggerLevel.INFO: self.info,
        }[level]

    def log(self, message, level: TestLoggerLevel = TestLoggerLevel.INFO, ident=2):
        self.level_to_function(level)(message, ident)

    def log_result_status(
        self, message, status: TestResultStatus = TestResultStatus.PASS, ident=2
    ):
        level = RESULT_STATUS_TO_LOG_LEVEL[status]
        self.log(message, level, ident)

    def log_status_list(self, message, statuses: list[TestResultStatus], ident=2):
        if TestResultStatus.FAIL in statuses:
            self.error(message, ident=ident)
        elif TestResultStatus.SOFT_FAIL in statuses:
            self.soft_error(message, ident=ident)
        elif TestResultStatus.PASS in statuses:
            self.success(message, ident=ident)


class ServerTestLogger(AbstractTestLogger):

    def __init__(self, channel: Channel) -> None:
        super().__init__()

        self.channel = channel

    def info(self, message, ident=2):
        self.log(message, TestLoggerLevel.INFO, ident=ident)

    def success(self, message, ident=2):
        self.log(message, TestLoggerLevel.SUCCESS, ident=ident)

    def soft_error(self, message, ident=2):
        self.log(message, TestLoggerLevel.SOFT_ERROR, ident=ident)

    def error(self, message, ident=2):
        self.log(message, TestLoggerLevel.ERROR, ident=ident)

    def log(self, message, level: TestLoggerLevel = TestLoggerLevel.INFO, ident=2):
        log_message = LogMessage(
            level=level.name, message=message, ident=ident, logger="test"
        )
        envelope = LogMessageEnvelope(message=log_message)
        # Done as a task to allow logging to by synchronous
        asyncio.create_task(self.channel.send(envelope))
