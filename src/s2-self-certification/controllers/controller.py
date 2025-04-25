from email import message
from typing import Awaitable, Callable, Type
from connection import Connection
from message_handlers import MessageHandler
from s2python.common import (
    ControlType as ProtocolControlType,
    PowerForecast,
    PowerMeasurement,
)
from s2python.message import S2Message
from s2python.s2_validation_error import S2ValidationError

import logging

logger = logging.getLogger(__name__)


class Controller(MessageHandler):
    control_type: ProtocolControlType

    messages_received = []

    def __init__(self):
        super().__init__()

    def handle_message(
        self, message: S2Message, connection: Connection, *args, **kwargs
    ):
        try:
            result = super().handle_message(message, connection, *args, **kwargs)
        except:
            raise
        finally:
            self.messages_received.append(message)
        return result or None

    def handle_s2_validation_exception(self, e: S2ValidationError):
        logger.error("Failed to validate S2 Message.")
        logger.error(e.pydantic_validation_error)

    def get_received_messages(self, message_type: Type[S2Message]) -> list:
        def filter_messages(m: S2Message):
            logger.info("Filter: %s, %s", type(m), message_type)
            return type(m) == message_type

        result = list(filter(filter_messages, self.messages_received))

        return result


class BaseController(Controller):
    control_type = ProtocolControlType.NOT_CONTROLABLE

    def __init__(self):
        super().__init__()

        self.add_handler(PowerMeasurement, self.handle_power_measurement_message)
        self.add_handler(PowerForecast, self.handle_power_forecast_message)

    async def handle_power_measurement_message(
        self,
        message: PowerMeasurement,
        connection: "Connection",
        send_okay: Awaitable,
    ):

        await send_okay

    async def handle_power_forecast_message(
        self,
        message: PowerForecast,
        connection: "Connection",
        send_okay: Awaitable,
    ):

        await send_okay
