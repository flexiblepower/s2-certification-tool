import asyncio
import json
import logging
import threading
import uuid
import abc
from typing import Type

import websockets
from s2python.common import ReceptionStatus, ReceptionStatusValues
from s2python.message import S2Message
from s2python.reception_status_awaiter import ReceptionStatusAwaiter
from s2python.s2_parser import S2Parser
from s2python.s2_validation_error import S2ValidationError

logger = logging.getLogger(__name__)


class SendOkay:
    """Mostly copied over from S2-Python library"""

    status_is_send: threading.Event
    connection: "BaseRMConnection"
    subject_message_id: uuid.UUID

    def __init__(self, connection: "BaseRMConnection", subject_message_id: uuid.UUID):
        self.status_is_send = threading.Event()
        self.connection = connection
        self.subject_message_id = subject_message_id

    async def run_async(self) -> None:
        self.status_is_send.set()

        await self.connection.respond_with_reception_status(
            subject_message_id=self.subject_message_id,
            status=ReceptionStatusValues.OK,
            diagnostic_label="Processed okay.",
        )

    async def ensure_send_async(self, type_msg: Type[S2Message]) -> None:
        if not self.status_is_send.is_set():
            logger.warning(
                "Handler for message %s %s did not call send_okay / function to send the ReceptionStatus. "
                "Sending it now.",
                type_msg,
                self.subject_message_id,
            )
            await self.run_async()


class BaseRMConnection(abc.ABC):  # pylint: disable=too-many-instance-attributes
    """
    Manged the websocket connection to the RM.
    Puts all received messages onto the message queue so they can be retrieved by other tasks.
    Based on the S2Connection class is S2-Python library.
    """

    s2_parser: S2Parser

    reception_status_awaiter: ReceptionStatusAwaiter

    message_queue: asyncio.Queue

    _stop_event: asyncio.Event

    def __init__(self) -> None:  # pylint: disable=too-many-arguments
        self.reception_status_awaiter = ReceptionStatusAwaiter()
        self.s2_parser = S2Parser()

        self._stop_event = asyncio.Event()

        self.message_queue = asyncio.Queue()

    @abc.abstractmethod
    async def send(self, message: str):
        pass

    @abc.abstractmethod
    async def receive(self):
        pass

    async def _send_and_forget(self, s2_msg: S2Message) -> None:
        json_msg = s2_msg.to_json()
        logger.info(json_msg)
        try:
            await self.send(json_msg)
        except websockets.ConnectionClosedError as e:
            logger.error("Unable to send message %s.", s2_msg.message_type)

    async def respond_with_reception_status(
        self,
        subject_message_id: uuid.UUID,
        status: ReceptionStatusValues,
        diagnostic_label: str,
    ) -> None:
        logger.debug(
            "Responding to message %s with status %s", subject_message_id, status
        )
        msg = ReceptionStatus(
            subject_message_id=subject_message_id,
            status=status,
            diagnostic_label=diagnostic_label,
        )
        await self._send_and_forget(msg)

    async def send_msg_and_await_reception_status(
        self,
        s2_msg: S2Message,
        timeout_reception_status: float = 5.0,
        raise_on_error: bool = True,
    ) -> ReceptionStatus:
        await self._send_and_forget(s2_msg)
        logger.debug(
            "Waiting for ReceptionStatus for %s %s seconds",
            s2_msg.message_id,  # type: ignore[attr-defined, union-attr]
            timeout_reception_status,
        )
        try:
            reception_status = await self.reception_status_awaiter.wait_for_reception_status(
                s2_msg.message_id, timeout_reception_status  # type: ignore[attr-defined, union-attr]
            )
        except TimeoutError:
            logger.error(
                "Did not receive a reception status on time for %s",
                s2_msg.message_id,  # type: ignore[attr-defined, union-attr]
            )
            self._stop_event.set()
            raise

        if reception_status.status != ReceptionStatusValues.OK and raise_on_error:
            raise RuntimeError(
                f"ReceptionStatus was not OK but rather {reception_status.status}"
            )

        return reception_status

    async def parse_received_message(self, message: str):
        try:
            s2_msg: S2Message = self.s2_parser.parse_as_any_message(message)
        except json.JSONDecodeError:
            await self._send_and_forget(
                ReceptionStatus(
                    subject_message_id=uuid.UUID(
                        "00000000-0000-0000-0000-000000000000"
                    ),
                    status=ReceptionStatusValues.INVALID_DATA,
                    diagnostic_label="Not valid json.",
                )
            )
        except S2ValidationError as e:
            json_msg = json.loads(message)
            message_id = json_msg.get("message_id")
            if message_id:
                await self.respond_with_reception_status(
                    subject_message_id=message_id,
                    status=ReceptionStatusValues.OK,  # TODO: Put this back to the correct error.
                    diagnostic_label="",
                    # status=ReceptionStatusValues.INVALID_MESSAGE,
                    # diagnostic_label=str(e),
                )
            else:
                await self.respond_with_reception_status(
                    subject_message_id=uuid.UUID(
                        "00000000-0000-0000-0000-000000000000"
                    ),
                    status=ReceptionStatusValues.OK,  # TODO: Put this back to the correct error.
                    diagnostic_label="",
                    # status=ReceptionStatusValues.INVALID_DATA,
                    # diagnostic_label="Message appears valid json but could not find a message_id field.",
                )

            # Raise the error so that we can handle it in the orchestrator
            raise e
        except websockets.ConnectionClosedOK:
            logger.info("Connection closed by remote. ")
            await self.stop()
        else:
            logger.debug("Processing message: %s", s2_msg.to_json())

            if isinstance(s2_msg, ReceptionStatus):
                logger.debug(
                    "Message is a reception status for %s so registering in cache.",
                    s2_msg.subject_message_id,
                )
                await self.reception_status_awaiter.receive_reception_status(s2_msg)
            else:
                await self.message_queue.put(s2_msg)

    async def receive_messages(self):
        while not self._stop_event.is_set():
            # Timeout was added so that this task can exit at some point since if it never receives another message it just sits waiting.
            try:
                message = await asyncio.wait_for(self.receive(), timeout=1)
                logger.debug("Received Message: %s", message)
            except asyncio.TimeoutError:
                continue

            await self.parse_received_message(str(message))

    async def get_next_message(self):
        return await self.message_queue.get()

    def stop(self):
        self._stop_event.set()
