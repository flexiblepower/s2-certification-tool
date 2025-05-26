import logging
import asyncio
import time
from typing import Dict

from s2python.common import (
    ControlType as ProtocolControlType,
    EnergyManagementRole,
    Handshake,
    SelectControlType,
    HandshakeResponse,
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
from .base_role_executor import (
    AbstractRoleExecutor,
    ExitMainLoopException,
    execute_as_test,
)

logger = logging.getLogger(__name__)


class CEMTestExecutor(AbstractRoleExecutor):
    role = EnergyManagementRole.CEM
    controller: BaseCEMController

    def __init__(
        self,
        controllers: Dict[ProtocolControlType, Controller],
        test_suite: TestSuite,
        report: ComplianceReport,
        test_logger: AbstractTestLogger,
    ) -> None:
        super().__init__(controllers, test_suite, report, test_logger)

        self._control_type_selected_event = asyncio.Event()

    @execute_as_test(
        test_name="9.2.2. Activate Control Type",
        error_message_prefix="Failed to activate control type",
    )
    async def handle_select_control_type(self, message: SelectControlType):
        logger.info("Control Type Selected: %s", message.control_type)
        self.set_control_type(message.control_type)
        self._control_type_selected_event.set()

    async def process_message(self, message: S2Message):
        if type(message) == SelectControlType:
            logger.info("SELECT CONTROL TYPE %s", message.control_type)
            await self.handle_select_control_type(message)
        return await super().process_message(message)

    @execute_as_test(
        test_name="9.2.1. Update Resource Manager Details",
        error_message_prefix="Error whilst sending RM Details:",
    )
    async def send_resource_manager_details(self, control_type: ProtocolControlType):
        try:
            if self.channel is None:
                raise ValueError("Channel not set.")

            # logger.info(self.controller.resource_manager_details.available_control_types)
            self.controller.resource_manager_details.available_control_types = [
                control_type
            ]
            await self.controller.send_resource_manager_details(self.channel)
            self.test_logger.success("Resource Manager Details Sent.", ident=0)
        except Exception as e:
            self.test_logger.error(
                f"Failed to send ResourceManagerDetails: {e}", ident=0
            )
            raise ExitMainLoopException()

    async def wait_for_select_control_type(self):
        try:
            await wait_for_event_or_stop(
                self._control_type_selected_event,
                self._stop_event,
                5,
                "Control Type Selected Event",
            )
            self.test_logger.success(
                f"Control type set to {self.controller.control_type.name}", ident=0
            )
        except asyncio.CancelledError:
            logger.warning("Main loop was cancelled.")
            raise  # Propagate for TaskGroup
        except Exception as e:
            self.test_logger.error(
                f"Failed to receive control type selection: {e}", ident=0
            )
            raise ExitMainLoopException()

    async def wait_for_handshake_response(self):
        try:
            await self.controller.message_awaiter.wait_for_message(HandshakeResponse, 5)
            self.test_logger.success("Handshake Response Received.", ident=0)
        except asyncio.CancelledError:
            logger.warning("Main loop was cancelled.")
            raise  # Propagate for TaskGroup
        except Exception as e:
            self.test_logger.error(f"No handshake response received: {e}", ident=0)
            return

    async def main_loop(self):
        # This sets the main loop started event so that the message processing can start.
        await super().main_loop()
        logger.info("Starting Main Loop for CEM Test Executor.")
        if self.channel is None:
            raise ValueError("Channel not set.")

        self.test_logger.info("Test suite starting. ", ident=0)
        try:
            await self.send_handshake()
            await self.wait_for_handshake()

            await self.wait_for_handshake_response()

            logger.info("Received Handshake from CEM. Sending RM Details.")
            if self.controller.resource_manager_details is None:
                raise ValueError("RM Details not set!")

            control_types = (
                self.controller.resource_manager_details.available_control_types
            )
            logger.info("Control Types: %s", control_types)
            for control_type in control_types:

                logger.info("Sending RM Details with %s control type.", control_type)
                # Reset control type selected event so everything waits.
                self._control_type_selected_event.clear()

                await self.send_resource_manager_details(control_type)

                await self.wait_for_select_control_type()

                await self.controller.after_chosen(self.channel)

                await self.execute_test_suite()

                await asyncio.sleep(5)

        except ExitMainLoopException:
            return
