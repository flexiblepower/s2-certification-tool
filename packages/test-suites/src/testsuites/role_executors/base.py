import abc
import asyncio
import logging
from typing import Dict, Optional

from s2python.common import (
    ControlType as ProtocolControlType,
    EnergyManagementRole,
)
from s2python.message import S2Message


from testsuites.certificate.certificate import ComplianceReport
from testsuites.test_suite.test_suite import TestSuite, TestSuiteBuilder
from testsuites.test_logger import (
    AbstractTestLogger,
)
from testsuites.controllers import (
    Controller,
)
from connectivity.s2_channel import S2Channel


logger = logging.getLogger(__name__)


class AbstractRoleExecutor(abc.ABC):
    # In the role executor the channel is only used for sending messages. Receiving messages handled by IntegrationTestExecutor.
    channel: Optional["S2Channel"] = None
    role: EnergyManagementRole

    controller: Controller
    controllers: Dict[ProtocolControlType, Controller]

    test_suite: TestSuite

    report: ComplianceReport
    test_logger: AbstractTestLogger

    _handshake_received_event: asyncio.Event
    _main_loop_started_event: asyncio.Event

    _stop_event: asyncio.Event

    def __init__(
        self,
        available_control_types: Dict[ProtocolControlType, Controller],
        test_suite: TestSuite,
        report: ComplianceReport,
        test_logger: AbstractTestLogger,
    ) -> None:

        self.controllers = available_control_types

        controller = available_control_types.get(ProtocolControlType.NO_SELECTION)
        if controller is None:
            raise ValueError("A NO_SELECTION controller must be provided.")
        self.controller = controller

        self.test_suite = test_suite

        self.report = report

        self.test_logger = test_logger

        self._handshake_complete = asyncio.Event()
        self._main_loop_started_event = asyncio.Event()

    async def run(self, channel: S2Channel, stop_event: asyncio.Event, *args, **kwargs):
        self.channel = channel
        self._stop_event = stop_event

        await self.main_loop()

    def set_control_type(self, control_type: ProtocolControlType):
        controller = self.controllers[control_type]
        # Put the RM Details into the new controller.
        controller.resource_manager_details = controller.resource_manager_details
        self.controller = controller

    async def process_message(self, message: S2Message):
        # This is just to make sure that the channel is set before any messages are processed
        await self._main_loop_started_event.wait()
        await self.controller.handle_message(message, self.channel)

    @abc.abstractmethod
    async def main_loop(self):
        self._main_loop_started_event.set()
        pass
