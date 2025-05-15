import uuid
import asyncio
from typing import Awaitable
from s2python.common import (
    ControlType as ProtocolControlType,
    EnergyManagementRole,
    PowerForecast,
    PowerMeasurement,
    Handshake,
    ResourceManagerDetails,
    HandshakeResponse,
    SessionRequest,
    SessionRequestType,
    SelectControlType,
)
from connectivity.s2_channel import S2Channel

from ..controller import Controller

from s2python.version import S2_VERSION

import logging

logger = logging.getLogger(__name__)


class BaseRMController(Controller):
    role = EnergyManagementRole.CEM
    control_type = ProtocolControlType.NO_SELECTION

    _resource_manager_details_received: asyncio.Event

    def __init__(self):
        super().__init__()

        self._resource_manager_details_received = asyncio.Event()

        self.add_handler(Handshake, self.handle_handshake)
        self.add_handler(ResourceManagerDetails, self.handle_rm_details)

        self.add_handler(PowerMeasurement, self.handle_power_measurement_message)
        self.add_handler(PowerForecast, self.handle_power_forecast_message)

    async def handle_handshake(
        self,
        message: Handshake,
        channel: "S2Channel",
        send_okay: Awaitable[None],
    ) -> None:

        if channel is None:
            raise ValueError("Channel not set.")

        logger.debug(
            "%s supports S2 protocol versions: %s",
            message.role,
            message.supported_protocol_versions,
        )
        if message.supported_protocol_versions is None:
            raise ValueError(
                "Missing supported protocol versions in handshake message."
            )

        await channel.send_msg_and_await_reception_status(
            HandshakeResponse(
                message_id=uuid.uuid4(),
                selected_protocol_version=message.supported_protocol_versions[0],
            )
        )
        await send_okay

    async def select_control_type(self, channel: "S2Channel"):
        await channel.send_msg_and_await_reception_status(
            # The controller is updated in executor before sending the selection. So we just use the current instance's type.
            SelectControlType(message_id=uuid.uuid4(), control_type=self.control_type)
        )

    async def handle_rm_details(
        self,
        message: ResourceManagerDetails,
        channel: "S2Channel",
        send_okay: Awaitable,
    ):
        self.resource_manager_details = message

        self._resource_manager_details_received.set()

        await send_okay

    async def wait_until_rm_details_received(self):
        await self._resource_manager_details_received.wait()

    async def perform_handshake(self, channel: S2Channel):
        if channel is None:
            raise ValueError("Channel not set.")

        await channel.send_msg_and_await_reception_status(
            Handshake(
                message_id=uuid.uuid4(),  # type: ignore
                role=self.role,
                supported_protocol_versions=[S2_VERSION],
            )
        )

    async def perform_disconnect(self, channel: "S2Channel"):
        await channel.send_msg_and_await_reception_status(
            SessionRequest(
                message_id=uuid.uuid4(),
                request=SessionRequestType.TERMINATE,
                diagnostic_label="Testing complete.",
            )
        )

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
