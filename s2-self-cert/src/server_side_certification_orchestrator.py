import asyncio
import logging
import uuid
from types import CoroutineType
from typing import Awaitable, Callable, Coroutine, Dict, Optional, Type

from s2testing.certificate.certificate import ComplianceReport
from s2python.common import ControlType as ProtocolControlType
from s2python.common import (
    EnergyManagementRole,
    Handshake,
    HandshakeResponse,
    ResourceManagerDetails,
    SelectControlType,
)
from s2python.message import S2Message
from s2python.s2_validation_error import S2ValidationError
from s2python.version import S2_VERSION


from s2testing.connection import BaseConnection
from s2testing.async_task_manager import AsyncTaskManager
from s2testing.orchestrator import Orchestrator
from s2testing.connection import SendOkay
from s2testing.controllers import Controller
from s2testing.test_suite.test_suite import TestSuite
from s2testing.util import wait_for_event_or_stop

logger = logging.getLogger(__name__)


class ServerSideCertificationOrchestrator(Orchestrator):
    connection: Optional["BaseConnection"] = None

    def __init__(
        self,
    ) -> None:
        super().__init__()

    async def process_message(self, message: str):
        # TODO: Send the message to the server
        pass

    async def main_loop(self):
        pass

    async def setup(self, connection: BaseConnection, *args, **kwargs):
        await super().setup(connection)

        # self.create_task(self.main_loop(), True)
