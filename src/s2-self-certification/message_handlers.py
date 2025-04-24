import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Tuple, Type

from s2python.common import ControlType as ProtocolControlType
from s2python.common import EnergyManagementRole, ResourceManagerDetails
from s2python.message import S2Message
from s2python.s2_connection import SendOkay

if TYPE_CHECKING:
    from connection import Connection

import logging

logger = logging.getLogger(__name__)

class MessageHandlerNotFoundError(Exception):
    pass


class S2MessageAwaiter:
    """
    Utility class which waits allows async functions on different threads
    to wait for a message of a particular type to be received.
    """

    awaiting: Dict[Type[S2Message], Tuple[asyncio.Event, Optional[S2Message]]]

    def __init__(self):
        self.awaiting = {}

    async def wait_for_message(self, message_type: Type[S2Message], timeout: float):
        # Incase we have multiple tasks waiting for the same message.
        # Not sure if this going to be a possible scenario, but worth covering anyways.
        if message_type not in self.awaiting or self.awaiting[message_type][0].is_set():
            event = asyncio.Event()
            self.awaiting[message_type] = (event, None)
        else:
            event = self.awaiting[message_type][0]

        await asyncio.wait_for(event.wait(), timeout)

        message = self.awaiting[message_type][1]
        if message is None:
            raise ValueError("Message not set.")

        return message

    def receive_message(self, message: S2Message):
        if message.message_type in self.awaiting:
            logger.debug("Received message that is being waited for. Setting event.")
            awaiting = self.awaiting[message.message_type]
            if self.awaiting:
                # Set the message first before triggering the event to make sure that the
                # waiting method gets the message.
                awaiting[1] = message  # type: ignore
                awaiting[0].set()
        else:
            logger.debug("Received message but nothing waiting for it.")


class MessageHandler:
    handlers: Dict[Type[S2Message], Callable]

    message_awaiter = S2MessageAwaiter()

    # When set to true messages without a handler won't thrown an error
    # and the okay response will be sent.
    _accept_unhandled_messages: bool = True

    def __init__(self):
        self.handlers = {}

        self.message_awaiter = S2MessageAwaiter()

    def is_correct_message_type(
        self, message: S2Message, message_type: Type[S2Message]
    ):
        if not isinstance(message, message_type):
            logger.error(
                "Handler for Handshake received a message of the wrong type: %s",
                type(message),
            )
            return False
        return True

    def add_handler(self, msg_type: Type[S2Message], handler: Callable):
        self.handlers[msg_type] = handler

    async def handle_message(
        self, message: S2Message, connection: "Connection", *args, **kwargs
    ):
        try:
            handler = self.handlers[type(message)]

            send_okay = SendOkay(connection, message.message_id)  # type: ignore[attr-defined, union-attr]

            self.message_awaiter.receive_message(message)
            result = await handler(
                message, connection, send_okay.run_async(), *args, **kwargs
            )

            await send_okay.ensure_send_async(type(message))

            return result

        except KeyError:
            if self._accept_unhandled_messages:
                send_okay = SendOkay(connection, message.message_id)  # type: ignore[attr-defined, union-attr]

                await send_okay.run_async()
            else:
                raise MessageHandlerNotFoundError(
                    f"Command does not exist for message type '{ message.message_type}'"
                )


ROLE = EnergyManagementRole.CEM
