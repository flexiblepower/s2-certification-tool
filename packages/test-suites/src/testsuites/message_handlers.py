import abc
import asyncio
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    Generic,
    Optional,
    Tuple,
    Type,
    TypeVar,
)

from s2python.common import EnergyManagementRole
from s2python.message import S2Message
from connectivity.s2_channel import SendOkay, S2Channel
import logging

from testsuites.envelope_models.certification_message import CertificationMessage
from testsuites.envelope_models.control_message import ControlMessage

logger = logging.getLogger(__name__)


class MessageHandlerNotFoundError(Exception):
    pass


T = TypeVar("T")  # Generic type for handler identifier
M = TypeVar("M")  # Generic type for message


class MessageHandler(abc.ABC, Generic[T, M]):
    """Abstract base class for message handlers with configurable identifier types.

    Provides a framework for dispatching messages to registered handlers based on
    message identifiers. Supports graceful handling of unregistered message types.
    """

    handlers: Dict[T, Callable[..., Awaitable[None]]]
    """Dictionary mapping message identifiers to their handler functions."""

    _accept_unhandled_messages: bool = True
    """If True, unhandled messages won't raise errors. Defaults to True."""

    def __init__(self):
        """Initialize the message handler with an empty handlers dictionary."""
        self.handlers = {}

    @abc.abstractmethod
    def get_message_identifier(self, message: M) -> T:
        """Extract the identifier used to select the appropriate handler.

        Args:
            message: The message to extract identifier from.

        Returns:
            The identifier used for handler lookup.
        """
        pass

    def add_handler(self, identifier: T, handler: Callable[..., Awaitable[None]]):
        """Register a handler for the given identifier.

        Args:
            identifier: The message identifier this handler processes.
            handler: Async function to handle messages with this identifier.
        """
        self.handlers[identifier] = handler

    async def handle_message(self, message: M, *args, **kwargs) -> Any:
        """Dispatch message to appropriate handler based on its identifier.

        Args:
            message: The message to handle.
            *args, **kwargs: Additional arguments passed to the handler.

        Raises:
            MessageHandlerNotFoundError: If no handler found and unhandled messages not accepted.

        Returns:
            Result from the handler if any.
        """
        identifier = self.get_message_identifier(message)

        try:
            handler = self.handlers[identifier]
            return await handler(message, *args, **kwargs)
        except KeyError:
            if not self._accept_unhandled_messages:
                raise MessageHandlerNotFoundError(
                    f"No handler found for identifier: {identifier}"
                )


class S2MessageHandler(MessageHandler[type, "S2Message"]):
    """Message handler for S2Message objects using message type as identifier.

    Extends the base MessageHandler to work specifically with S2Message objects,
    automatically handling okay responses and message validation.
    """

    def get_message_identifier(self, message: "S2Message") -> type:
        """Get the message type as identifier.

        Args:
            message: The S2Message to get the type from.

        Returns:
            The type of the message used for handler lookup.
        """
        return type(message)

    def is_correct_message_type(
        self, message: "S2Message", message_type: type, raise_exception=True
    ) -> bool:
        """Check if message matches expected type.

        Args:
            message: The message to validate.
            message_type: The expected message type.
            raise_exception: If True, raises ValueError on type mismatch.

        Raises:
            ValueError: If message type doesn't match and raise_exception is True.

        Returns:
            True if message type matches, False otherwise.
        """
        if not isinstance(message, message_type):
            logger.error(
                "Handler received wrong message type: %s, expected: %s",
                type(message),
                message_type,
            )
            if raise_exception:
                raise ValueError(
                    f"Expected {message_type} but received {type(message)}"
                )
            return False
        return True

    async def handle_message(self, message: "S2Message", channel: "S2Channel") -> Any:
        """Handle S2Message with automatic okay response.

        Processes the message through the appropriate handler and automatically
        sends an okay response back through the channel.

        Args:
            message: The S2Message to handle.
            channel: The channel to send responses through.

        Raises:
            MessageHandlerNotFoundError: If no handler found and unhandled messages not accepted.

        Returns:
            Result from the message handler if any.
        """
        identifier = self.get_message_identifier(message)

        try:
            handler = self.handlers[identifier]
            send_okay = SendOkay(channel, message.message_id)  # type: ignore

            result = await handler(message, channel, send_okay.run_async())
            await send_okay.ensure_send_async(identifier)

            return result
        except KeyError:
            if self._accept_unhandled_messages:
                send_okay = SendOkay(channel, message.message_id)  # type: ignore
                await send_okay.run_async()
            else:
                raise MessageHandlerNotFoundError(
                    f"No handler for message type: {getattr(message, 'message_type', identifier)}"
                )


class CertificationMessageHandler(MessageHandler[type, "CertificationMessage"]):

    def get_message_identifier(self, message: "S2Message") -> type:
        """Get the message type as identifier.

        Args:
            message: The CertificationMessage to get the type from.

        Returns:
            The type of the message used for handler lookup.
        """
        return type(message)

class ControlMessageHandler(MessageHandler[type, "ControlMessage"]):

    def get_message_identifier(self, message: "S2Message") -> type:
        """Get the message type as identifier.

        Args:
            message: The CertificationMessage to get the type from.

        Returns:
            The type of the message used for handler lookup.
        """
        return type(message)