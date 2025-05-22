from typing import Optional
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

from .base import BaseCEMController


class NotControllableCEMController(BaseCEMController):
    control_type = ProtocolControlType.NOT_CONTROLABLE

    power_measurements: list[PowerMeasurement] = []
    power_forecasts: list[PowerForecast] = []

    _save_power_forecasts = False
    _save_power_measurements = False

    async def send_power_measurement(
        self, channel: Optional[S2Channel], power_measurement: PowerMeasurement
    ):
        if channel is None:
            raise ValueError("Channel not set.")

        await channel.send_msg_and_await_reception_status(power_measurement)

        if self._save_power_measurements:
            self.power_measurements.append(power_measurement)
        else:
            self.power_measurements = [power_measurement]

    async def send_power_forecast(
        self, channel: Optional[S2Channel], power_forecast: PowerForecast
    ):
        if channel is None:
            raise ValueError("Channel not set.")

        await channel.send_msg_and_await_reception_status(power_forecast)

        if self._save_power_forecasts:
            self.power_forecasts.append(power_forecast)
        else:
            self.power_forecasts = [power_forecast]

    # async def revoke_power_forecast(
    #     self,
    #     channel: Optional[S2Channel],
    #     power_forecast: Optional[PowerForecast] = None,
    # ):
    #     if channel is None:
    #         raise ValueError("Channel not set.")

    #     if power_forecast is None and len(self.power_forecasts) > 0:
    #         power_forecast = self.power_forecasts[-1]

    #     if power_forecast is None:
    #         raise ValueError("No power forecast to use.")

    #     await channel.send_msg_and_await_reception_status(RevokeObject(
    #         object_id=power_forecast.message_id,
    #         object_type=RevokableObjects.P
    #     ))
