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

    def __init__(self):
        super().__init__()

    def handle_s2_validation_exception(self, e: S2ValidationError):
        logger.error("Failed to validate S2 Message.")
        logger.error(e.pydantic_validation_error)


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
