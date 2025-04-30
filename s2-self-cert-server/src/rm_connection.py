import asyncio
import json
import logging
import uuid
from typing import Type

from fastapi import WebSocket
from starlette.websockets import WebSocketClose
from s2testing.connection import BaseRMConnection
from s2python.message import S2Message

from .client_connection import ClientConnection
from .model import (
    ControlMessageEnvelope,
    MessageEnvelopeTypeEnum,
    S2MessageEnvelope,
    ServerMessage,
    ServerMessageValidationException,
)

logger = logging.getLogger(__name__)


class RMConnection(BaseRMConnection):
    """
    RMConnection is an implementation of BaseRMConnection used for server-side testing.
    
    This class facilitates communication with the RM (Resource Manager) via the local s2-self-cert instance.
    S2Messages are encapsulated in an envelope for transmission between the client and server sides.
    The client side is responsible for unwrapping the envelope and forwarding the S2Message to the physical RM.
    
    Attributes:
      receive_queue (asyncio.Queue): Queue which received messages are put onto.
      client_connection (ClientConnection): The connection to the local instance which is used to send the message via the WS.
    """

    receive_queue: asyncio.Queue
    client_connection: ClientConnection

    def __init__(self, client_connection: ClientConnection):
        super().__init__()

        self.receive_queue = asyncio.Queue()
        self.client_connection = client_connection

    async def send(self, message: S2Message):
        await self.client_connection.send_s2_message(message)

    async def receive(self):
        msg = await self.receive_queue.get()

        logger.info(f"Received S2 message: {msg} ")

    async def add_message_to_queue(self, message: dict):
        await self.receive_queue.put(message)
