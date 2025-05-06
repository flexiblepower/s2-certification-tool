import asyncio
from typing import Awaitable, Callable, Optional, Type
import uuid
from testsuites.message_handlers import MessageHandler
from s2python.common import (
    ControlType as ProtocolControlType,
    PowerForecast,
    PowerMeasurement,
    ResourceManagerDetails,
)
from s2python.message import S2Message
from s2python.common import (
    Handshake,
    HandshakeResponse,
    SelectControlType,
    EnergyManagementRole,
)
from s2python.s2_validation_error import S2ValidationError
from connectivity.s2_channel import S2Channel, SendOkay

from testsuites.util import wait_for_event_or_stop
from s2python.version import S2_VERSION
import logging

logger = logging.getLogger(__name__)


class Controller(MessageHandler):
    control_type: ProtocolControlType

    role: EnergyManagementRole = EnergyManagementRole.CEM

    resource_manager_details: Optional[ResourceManagerDetails] = None

    _resource_manager_details_received: asyncio.Event

    messages_received = []

    def __init__(self):
        super().__init__()

        self._resource_manager_details_received = asyncio.Event()

        self.add_handler(Handshake, self.handle_handshake)
        self.add_handler(ResourceManagerDetails, self.handle_rm_details)

    def handle_message(self, message: S2Message, channel: Optional[S2Channel]):
        if channel is None:
            raise ValueError("Channel must be provided.")
        try:
            result = super().handle_message(message, channel)
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
            return type(m) == message_type

        result = list(filter(filter_messages, self.messages_received))

        return result

    def handshake_acknowledged(self):
        # The CEM sends a handshake message. Once the RM sends HandshakeResponse this method should be called.
        pass

    def handshake_received(self):
        # After the handshake message is sent by the RM and the CEM (this program) responds with a HandshakeResponse
        # and receives a valid status response, then this method is called.
        pass

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

        # if not await wait_for_event_or_stop(self._handshake_complete, stop_event):
        #     return

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

        await send_okay

        await channel.send_msg_and_await_reception_status(
            HandshakeResponse(
                message_id=uuid.uuid4(),
                selected_protocol_version=message.supported_protocol_versions[0],
            )
        )

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

        await send_okay

        self._resource_manager_details_received.set()

    async def wait_until_rm_details_received(self):
        await self._resource_manager_details_received.wait()


class BaseController(Controller):
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
