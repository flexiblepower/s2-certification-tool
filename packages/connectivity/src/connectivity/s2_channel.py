import asyncio
import json
from typing import Optional, Type
import uuid
from s2python.common import ReceptionStatus, ReceptionStatusValues
from s2python.message import S2Message
from s2python.reception_status_awaiter import ReceptionStatusAwaiter
from s2python.s2_parser import S2Parser
from s2python.s2_validation_error import S2ValidationError
from connectivity.async_task_manager import AsyncTaskManager
from connectivity.connection_adapter import ConnectionAdapter

from .channel import Channel

import logging

logger = logging.getLogger(__name__)


class SendOkay:
    """Mostly copied over from S2-Python library"""

    status_is_send: asyncio.Event
    s2_channel: "S2Channel"
    subject_message_id: uuid.UUID

    def __init__(self, s2_channel: "S2Channel", subject_message_id: uuid.UUID):
        self.status_is_send = asyncio.Event()
        self.s2_channel = s2_channel
        self.subject_message_id = subject_message_id

    async def run_async(self) -> None:
        self.status_is_send.set()

        await self.s2_channel.respond_with_reception_status(
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


class S2Channel(Channel[S2Message, str]):

    s2_parser: S2Parser

    reception_status_awaiter: ReceptionStatusAwaiter

    def __init__(self, connection: ConnectionAdapter) -> None:
        super().__init__(connection)

        self.reception_status_awaiter = ReceptionStatusAwaiter()
        self.s2_parser = S2Parser()

        self.message_queue = asyncio.Queue()

    async def send(self, message: S2Message):
        # str_msg = message.model_dump_json()
        str_msg = message.to_json()

        return await self.connection.send(str_msg)

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
        await self.send(msg)

    async def send_msg_and_await_reception_status(
        self,
        s2_msg: S2Message,
        timeout_reception_status: float = 5,
        raise_on_error: bool = True,
    ) -> ReceptionStatus:
        await self.send(s2_msg)
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
            raise

        if reception_status.status != ReceptionStatusValues.OK and raise_on_error:
            raise RuntimeError(
                f"ReceptionStatus was not OK but rather {reception_status.status}"
            )

        return reception_status

    async def process_received_message(self, message: str) -> S2Message | None:
        try:
            s2_msg: S2Message = self.s2_parser.parse_as_any_message(message)
        except json.JSONDecodeError:
            await self.send(
                ReceptionStatus(
                    subject_message_id=uuid.UUID(
                        "00000000-0000-0000-0000-000000000000"
                    ),
                    status=ReceptionStatusValues.INVALID_DATA,
                    diagnostic_label="Not valid json.",
                )
            )
            raise
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
        else:
            if isinstance(s2_msg, ReceptionStatus):
                logger.debug(
                    "Message is a reception status for %s so registering in cache.",
                    s2_msg.subject_message_id,
                )
                await self.reception_status_awaiter.receive_reception_status(s2_msg)
            else:
                await self.message_queue.put(s2_msg)
