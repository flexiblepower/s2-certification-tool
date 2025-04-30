import asyncio
import json
import logging
import uuid
from typing import Type

from fastapi import WebSocket
from starlette.websockets import WebSocketClose
from test.ann_module import pars
from s2python.common import ReceptionStatus, ReceptionStatusValues
from s2python.message import S2Message
from s2python.reception_status_awaiter import ReceptionStatusAwaiter
from s2python.s2_parser import S2Parser
from s2python.s2_validation_error import S2ValidationError
from .model import (
    ControlMessageEnvelope,
    MessageEnvelopeTypeEnum,
    S2MessageEnvelope,
    ServerMessage,
    ServerMessageValidationException,
)

logger = logging.getLogger(__name__)


class ClientConnection:
    ws: WebSocket

    message_queue: asyncio.Queue

    _stop_event: asyncio.Event

    def __init__(self, ws) -> None:
        self.ws = ws

        self._stop_event = asyncio.Event()

        self.message_queue = asyncio.Queue()

    async def send_message(self, message: ServerMessage) -> None:
        if self.ws is None:
            raise RuntimeError(
                "Cannot send messages if websocket connection is not yet established."
            )

        await self.ws.send_json(message.model_dump())

    async def send_s2_message(self, message: S2Message):
        envelope = S2MessageEnvelope(message=message)
        await self.send_message(envelope)

    async def handle_received_message(self, message: dict):
        try:
            message_type = MessageEnvelopeTypeEnum(message["message_type"])

            parsed_message = None
            if message_type == MessageEnvelopeTypeEnum.LOG:
                logger.warning("Received log message from client. Ignoring.")
                pass
                # raise ValueError("Server cannot receive log messages.")
            elif message_type == MessageEnvelopeTypeEnum.S2:
                parsed_message = S2MessageEnvelope.model_validate(message)
                logger.info("Received S2 Message: %s", parsed_message)
            elif message_type == MessageEnvelopeTypeEnum.CONTROL:
                parsed_message = ControlMessageEnvelope.model_validate(message)
                logger.info("Received Control Message: %s", parsed_message)

            if parsed_message is not None:
                await self.message_queue.put(parsed_message)

        except KeyError:
            raise ServerMessageValidationException("Message must have a message type.")

    async def receive_messages(self):
        if self.ws is None:
            raise RuntimeError(
                "Cannot receive messages if websocket connection is not yet established."
            )
        logger.debug("Connection has started to receive messages.")

        # Timeout was added so that this task can exit at some point since if it never receives another message it just sits waiting.
        try:
            while not self._stop_event.is_set():
                try:
                    message = await self.ws.receive_json()
                    # message = await asyncio.wait_for(self.ws.receive_json(), timeout=1)
                except asyncio.TimeoutError:
                    continue

                if isinstance(message, WebSocketClose):
                    logger.info("Received WebSocket close message.")
                    self.stop()
                    break
                logger.info("Received Message: %s", message)
                await self.handle_received_message(message)

        except asyncio.CancelledError:
            logger.exception("Cancelled error thrown.")
        except RuntimeError as e:
            logger.info("WebSocket connection closed (RuntimeError): %s", e)
        except Exception as e:
            logger.exception("Exception while receiving message:")
        finally:
            self.stop()

    async def run(self):
        await self.receive_messages()

        await self.ws.close()

    async def get_next_message(self) -> ServerMessage:
        return await self.message_queue.get()

    def stop(self):
        self._stop_event.set()
