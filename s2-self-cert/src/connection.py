import asyncio
import json
import logging
import threading
import uuid
from typing import Type

import websockets
from s2python.common import ReceptionStatus, ReceptionStatusValues
from s2python.message import S2Message
from s2python.reception_status_awaiter import ReceptionStatusAwaiter
from s2python.s2_parser import S2Parser
from s2python.s2_validation_error import S2ValidationError
from websockets.asyncio.connection import Connection as WSConnection
from s2testing.connection import BaseRMConnection

logger = logging.getLogger(__name__)


class Connection(BaseRMConnection):  # pylint: disable=too-many-instance-attributes
    """
    Manged the websocket connection to the RM.
    Puts all received messages onto the message queue so they can be retrieved by other tasks.
    Based on the S2Connection class is S2-Python library.
    """

    ws: WSConnection

    def __init__(self, ws) -> None:  # pylint: disable=too-many-arguments
        super().__init__()
        self.ws = ws

    async def send(self, message):
        if self.ws is None:
            raise RuntimeError(
                "Cannot send messages if websocket connection is not yet established."
            )

        await self.ws.send(message)

    async def receive(self):
        if self.ws is None:
            raise RuntimeError(
                "Cannot receive messages if websocket connection is not yet established."
            )

        return await self.ws.recv()

    async def receive_messages(self):
        if self.ws is None:
            raise RuntimeError(
                "Cannot receive messages if websocket connection is not yet established."
            )
        logger.debug("Connection has started to receive messages.")

        try:
            await super().receive_messages()
        except websockets.ConnectionClosedOK:
            logger.info("Connection closed normally by remote.")
            self._handle_ws_close()
        except websockets.ConnectionClosedError as e:
            logger.error("Connection closed with error: %s", str(e))
            self._handle_ws_close()
        except asyncio.CancelledError:
            pass

    def _handle_ws_close(self):
        self._stop_event.set()

    async def stop(self):
        super().stop()

        await self.ws.close()
