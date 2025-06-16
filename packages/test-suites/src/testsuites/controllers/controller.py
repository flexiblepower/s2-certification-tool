import abc
import logging
import asyncio
import uuid
from typing import Awaitable, Callable, Optional, Type
from testsuites.message_handlers import S2MessageHandler
from s2python.common import (
    ControlType as ProtocolControlType,
    PowerForecast,
    PowerMeasurement,
    ResourceManagerDetails,
)
from s2python.version import S2_VERSION
from s2python.message import S2Message
from s2python.common import (
    Handshake,
    HandshakeResponse,
    SelectControlType,
    EnergyManagementRole,
    SessionRequest,
    SessionRequestType,
)
from s2python.s2_validation_error import S2ValidationError
from connectivity.s2_channel import S2Channel

logger = logging.getLogger(__name__)


class Controller(S2MessageHandler):
    control_type: ProtocolControlType

    role: EnergyManagementRole

    resource_manager_details: Optional[ResourceManagerDetails] = None

    messages_received = []

    _handshake_received_event: asyncio.Event

    def __init__(self):
        super().__init__()

        self._handshake_received_event = asyncio.Event()

    async def handle_message(self, message: S2Message, channel: Optional[S2Channel]):
        if channel is None:
            raise ValueError("Channel must be provided.")
        try:
            result = await super().handle_message(message, channel)
        except:
            raise
        finally:
            # Add all messages to the list so tests can find them.
            self.messages_received.append(message)
        return result

    def handle_s2_validation_exception(self, e: S2ValidationError):
        logger.error("Failed to validate S2 Message.")
        logger.error(e.pydantic_validation_error)

    def get_received_messages(self, message_type: Type[S2Message]) -> list:
        def filter_messages(m: S2Message):
            return type(m) == message_type

        result = list(filter(filter_messages, self.messages_received))

        return result

    async def send_handshake(self, channel: S2Channel, message: Handshake):
        if channel is None:
            raise ValueError("Channel not set.")

        await channel.send_msg_and_await_reception_status(message)

    async def handle_handshake(
        self,
        message: Handshake,
        channel: "S2Channel",
        send_okay: Awaitable[None],
    ) -> None:

        if channel is None:
            raise ValueError("Channel not set.")
        self._handshake_received_event.set()

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

    async def after_chosen(self, channel: Optional[S2Channel]):
        """
        This method should be run after the controller is set
        and should send any init messages for that control type."""
        pass
