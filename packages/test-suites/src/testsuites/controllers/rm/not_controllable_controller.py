from typing import Awaitable, Optional
from s2python.common import (
    ControlType as ProtocolControlType,
    EnergyManagementRole,
    PowerForecast,
    PowerMeasurement,
    ResourceManagerDetails,
    Handshake,
    RevokeObject,
    RevokableObjects,
)
from connectivity.s2_channel import S2Channel
from .base import BaseRMController


class NotControllableRMController(BaseRMController):
    control_type = ProtocolControlType.NOT_CONTROLABLE

    def __init__(self):
        super().__init__()

        self.add_handler(PowerMeasurement, self.handle_power_measurement_message)
        self.add_handler(PowerForecast, self.handle_power_forecast_message)

    async def handle_power_measurement_message(
        self,
        message: PowerMeasurement,
        channel: "S2Channel",
        send_okay: Awaitable,
    ):

        await send_okay

    async def handle_power_forecast_message(
        self,
        message: PowerForecast,
        channel: "S2Channel",
        send_okay: Awaitable,
    ):

        await send_okay
