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

    async def handle_handshake(
        self,
        message: Handshake,
        channel: "S2Channel",
        send_okay: Awaitable[None],
    ) -> None:

        await super().handle_handshake(message, channel, send_okay)

        await channel.send_msg_and_await_reception_status(
            HandshakeResponse(
                message_id=uuid.uuid4(),
                selected_protocol_version=message.supported_protocol_versions[0],  # type: ignore
            )
        )

    async def send_select_control_type(self, channel: "S2Channel"):
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

    async def wait_until_rm_details_received(self) -> ResourceManagerDetails:
        message = await self.message_awaiter.wait_for_message(
            ResourceManagerDetails, timeout=5
        )
        # await self._resource_manager_details_received.wait()

        if type(message) != ResourceManagerDetails:
            raise ValueError("Expected a Resource Manager details message.")
        return message

    async def send_session_request_disconnect(self, channel: "S2Channel"):
        await channel.send_msg_and_await_reception_status(
            SessionRequest(
                message_id=uuid.uuid4(),
                request=SessionRequestType.TERMINATE,
                diagnostic_label="Testing complete.",
            )
        )
