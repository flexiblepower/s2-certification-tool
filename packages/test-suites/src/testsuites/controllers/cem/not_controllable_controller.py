from typing import Optional
import uuid
from s2python.common import (
    ControlType as ProtocolControlType,
    EnergyManagementRole,
    PowerForecast,
    PowerMeasurement,
    ResourceManagerDetails,
    Handshake,
    RevokeObject,
    RevokableObjects,
    ReceptionStatus,
)
from connectivity.s2_channel import S2Channel

from .base import BaseCEMController


class NotControllableCEMController(BaseCEMController):
    control_type = ProtocolControlType.NOT_CONTROLABLE

    power_measurements: list[PowerMeasurement] = []
    power_forecasts: list[PowerForecast] = []

    _save_power_forecasts = False
    _save_power_measurements = False

    async def send_power_measurement(
        self, channel: Optional[S2Channel], power_measurement: PowerMeasurement
    ) -> ReceptionStatus:
        if channel is None:
            raise ValueError("Channel not set.")

        reception_status = await channel.send_msg_and_await_reception_status(
            power_measurement, raise_on_error=False
        )

        if self._save_power_measurements:
            self.power_measurements.append(power_measurement)
        else:
            self.power_measurements = [power_measurement]

        return reception_status

    async def send_power_forecast(
        self, channel: Optional[S2Channel], power_forecast: PowerForecast
    ) -> ReceptionStatus:
        if channel is None:
            raise ValueError("Channel not set.")

        reception_status = await channel.send_msg_and_await_reception_status(
            power_forecast, raise_on_error=False
        )

        if self._save_power_forecasts:
            self.power_forecasts.append(power_forecast)
        else:
            self.power_forecasts = [power_forecast]

        return reception_status

    # Power Forecast not revokable in S2-Python
