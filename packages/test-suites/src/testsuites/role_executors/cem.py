import logging
import asyncio
from typing import Dict

from s2python.common import (
    ControlType as ProtocolControlType,
    EnergyManagementRole,
    Handshake,
    SelectControlType,
)
from s2python.message import S2Message


from testsuites.util import wait_for_event_or_stop
from testsuites.certificate.certificate import ComplianceReport
from testsuites.test_suite.test_suite import TestSuite, TestSuiteBuilder
from testsuites.test_logger import (
    AbstractTestLogger,
)
from testsuites.controllers import (
    Controller,
    BaseCEMController,
)
from .base import AbstractRoleExecutor

logger = logging.getLogger(__name__)


class CEMTestExecutor(AbstractRoleExecutor):
    role = EnergyManagementRole.CEM
    controller: BaseCEMController

    def __init__(
        self,
        available_control_types: Dict[ProtocolControlType, Controller],
        test_suite: TestSuite,
        report: ComplianceReport,
        test_logger: AbstractTestLogger,
    ) -> None:
        super().__init__(available_control_types, test_suite, report, test_logger)

        self._control_type_selected_event = asyncio.Event()

    async def handle_select_control_type(self, message: SelectControlType):
        control_type = message.control_type

        try:
            self.set_control_type(control_type)
        except KeyError:
            raise ValueError("Invalid control type selection...")

    async def process_message(self, message: S2Message):
        if type(message) == SelectControlType:
            await self.handle_select_control_type(message)
        return await super().process_message(message)

    async def main_loop(self):
        # This sets the main loop started event so that the message processing can start.
        await super().main_loop()

        if self.channel is None:
            raise ValueError("Channel not set.")

        logger.info("Test suite starting.")

        try:
            await self.controller.perform_handshake(self.channel)
            self.test_logger.success("Handshake Message Sent", ident=0)
        except Exception as e:
            self.test_logger.error(f"Sending Handshake Message Failed: {e}", ident=0)
            return

        try:
            await wait_for_event_or_stop(
                self.controller._handshake_received_event,
                self._stop_event,
                description="Handshake received event.",
            )
            self.test_logger.success("Handshake Received.", ident=0)
        except Exception as e:
            self.test_logger.error(f"No handshake received: {e}", ident=0)
            return

        logger.info("Received Handshake from CEM. Sending RM Details.")

        try:
            await self.controller.send_resource_manager_details(self.channel)
        except Exception as e:
            self.test_logger.error(
                f"Failed to send ResourceManagerDetails: {e}", ident=0
            )
            return

        control_type_message = await self.controller.message_awaiter.wait_for_message(
            SelectControlType, timeout=5
        )

        if type(control_type_message) == SelectControlType:
            logger.info("Control Type Selected: %s", control_type_message.control_type)
            self.set_control_type(control_type_message.control_type)
