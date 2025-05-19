import asyncio
import uuid
from typing import Awaitable


from s2python.version import S2_VERSION
from s2python.common import (
    ControlType as ProtocolControlType,
    EnergyManagementRole,
    PowerForecast,
    PowerMeasurement,
    ResourceManagerDetails,
    Handshake,
)
from connectivity.s2_channel import S2Channel

from ..controller import Controller

import logging

logger = logging.getLogger(__name__)


class BaseCEMController(Controller):
    role = EnergyManagementRole.RM
    control_type = ProtocolControlType.NO_SELECTION

    def __init__(self, resource_manager_details: ResourceManagerDetails):
        super().__init__()

        self.resource_manager_details = resource_manager_details

        self._handshake_received_event = asyncio.Event()

        self.add_handler(Handshake, self.handle_handshake)

    async def handle_handshake(
        self, message: Handshake, channel: S2Channel, send_okay: Awaitable[None]
    ):
        logger.info("Received Handshake message: %s", message)
        self._handshake_received_event.set()

        await send_okay

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

    async def send_resource_manager_details(self, channel: S2Channel):
        if self.resource_manager_details is None:
            raise ValueError("Resource Manager Details must be set.")
        await channel.send_msg_and_await_reception_status(self.resource_manager_details)
