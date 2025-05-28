import asyncio
from typing import Awaitable, Callable, Dict, Optional, Tuple, Type

from s2python.common import EnergyManagementRole
from s2python.message import S2Message
from connectivity.s2_channel import SendOkay, S2Channel
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
    exit_event: Optional[asyncio.Event]

    def __init__(self, exit_event: Optional[asyncio.Event] = None):
        self.awaiting = {}
        self.exit_event = exit_event

    async def wait_for_message(
        self, message_type: Type[S2Message], timeout: float
    ) -> S2Message:
        """
        Waits for a given message type to be received.

        Args:
            message_type (type(S2Message)): The S2 Message Class that will be waited for. The return of this function will be a message of that type (if one is received).
            timeout (float): Time after which a TimeOut error will be thrown
        Returns:
            S2Message of type `message_type`. Unfortunately I can't get the type inference to be more granular on the output type.
        """

        # Incase we have multiple tasks waiting for the same message.
        # Not sure if this going to be a possible scenario, but worth covering anyways.
        if message_type not in self.awaiting or self.awaiting[message_type][0].is_set():
            event = asyncio.Event()
            self.awaiting[message_type] = (event, None)
        else:
            event = self.awaiting[message_type][0]

        try:
            await asyncio.wait_for(event.wait(), timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(
                f"No {message_type} message received within the specified timeout window"
            )

        message = self.awaiting[message_type][1]
        if message is None:
            raise ValueError("Message not set.")

        return message

    def receive_message(self, message: S2Message):
        if type(message) in self.awaiting:
            logger.info(
                "Received %s message that is being waited for. Setting event.",
                message.message_type,
            )
            event = self.awaiting[type(message)][0]

            # Set the message first before triggering the event to make sure that the
            # waiting method gets the message.
            self.awaiting[type(message)] = (event, message)

            event.set()
        else:
            logger.info("Received %s message. Nothing waiting for it.", type(message))


async def send_okay_message(channel: S2Channel, message: S2Message):
    send_okay = SendOkay(channel, message.message_id)  # type: ignore[attr-defined, union-attr]
    await send_okay.run_async()
    await send_okay.ensure_send_async(type(message))


class MessageHandler:
    handlers: Dict[Type[S2Message], Callable[..., Awaitable[None]]]

    message_awaiter = S2MessageAwaiter()

    # When set to true messages without a handler won't thrown an error
    # and the okay response will be sent.
    _accept_unhandled_messages: bool = True

    def __init__(self):
        self.handlers = {}

        self.message_awaiter = S2MessageAwaiter()

    def is_correct_message_type(
        self, message: S2Message, message_type: Type[S2Message], raise_exception=True
    ):
        if not isinstance(message, message_type):
            logger.error(
                "Handler for Handshake received a message of the wrong type: %s",
                type(message),
            )
            if raise_exception:
                raise ValueError(
                    f"Incorrect message type. Expected {message_type} but received {message.message_type}."
                )
            return False
        return True

    def add_handler(
        self, msg_type: Type[S2Message], handler: Callable[..., Awaitable[None]]
    ):
        self.handlers[msg_type] = handler

    async def handle_message(self, message: S2Message, channel: "S2Channel"):
        try:

            handler = self.handlers[type(message)]

            send_okay = SendOkay(channel, message.message_id)  # type: ignore[attr-defined, union-attr]

            result = await handler(message, channel, send_okay.run_async())

            await send_okay.ensure_send_async(type(message))

            return result

        except KeyError:
            if self._accept_unhandled_messages:
                send_okay = SendOkay(channel, message.message_id)  # type: ignore[attr-defined, union-attr]

                await send_okay.run_async()
            else:
                raise MessageHandlerNotFoundError(
                    f"Command does not exist for message type '{ message.message_type }'"
                )
        finally:
            self.message_awaiter.receive_message(message)


ROLE = EnergyManagementRole.CEM
