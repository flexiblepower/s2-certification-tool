import asyncio
from datetime import datetime
import logging
from typing import Dict, Optional

from s2python.common import ControlType as ProtocolControlType
from s2python.message import S2Message


from testsuites.certificate.certificate import ComplianceReport
from testsuites.test_suite.test_suite import TestSuite, TestSuiteBuilder
from testsuites.test_suite import FRBCTestCase, PEBCTestCase
from testsuites.controllers import (
    Controller,
    BaseController,
    PEBCController,
    FRBCController,
)


from connectivity.async_task_manager import AsyncTaskManager
from connectivity.s2_channel import S2Channel
from connectivity.config import Config


logger = logging.getLogger(__name__)


class IntegrationTestExecutor(AsyncTaskManager):

    # The channel which connects to the S2 RM.
    channel: Optional["S2Channel"] = None

    controller: Controller
    controllers: Dict[ProtocolControlType, Controller]

    test_suite: TestSuite

    report: ComplianceReport

    def __init__(
        self,
        available_control_types: Dict[ProtocolControlType, Controller],
        test_suite: TestSuite,
        report: ComplianceReport,
    ) -> None:
        super().__init__()

        self.controllers = available_control_types

        controller = available_control_types.get(ProtocolControlType.NO_SELECTION)
        if controller is None:
            raise ValueError("A NO_SELECTION controller must be provided.")
        self.controller = controller

        self.test_suite = test_suite

        self.report = report

    def set_control_type(self, control_type: ProtocolControlType):
        controller = self.controllers[control_type]
        # Put the RM Details into the new controller.
        controller.resource_manager_details = controller.resource_manager_details
        self.controller = controller

    async def process_message(self, message: S2Message):
        await self.controller.handle_message(message, self.channel)

    async def process_received_messages(self):
        """AsyncIO task which pops messages off the queue and processes them using the control type."""

        if self.channel is None:
            raise ValueError("Channel not set.")

        try:
            while not self._stop_event.is_set():
                try:
                    # Use a timeout to periodically check for cancellation
                    message = await asyncio.wait_for(
                        self.channel.get_next_message(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue  # Check stop event and loop again

                logger.info(message)
                await self.process_message(message)
        except asyncio.CancelledError:
            logger.info("Message Channel cancelled.")
        except Exception as e:
            logger.exception("Message processor encountered an error: %s", e)
        finally:
            await self.stop()

    async def execute_test_suite(self):
        # Wait until the handshake is complete before starting the testing.
        # TODO: Figure out how to include the handshake process in the testing.

        if self.channel is None:
            raise ValueError("Channel not set.")

        if self.controller:
            await self.test_suite.execute(self.channel, self.controller)

    async def main_loop(self):
        logger.info("Starting Main Loop.")
        if self.channel is None:
            raise ValueError("Channel not set.")

        await self.controller.perform_handshake(self.channel)

        await self.controller.wait_until_rm_details_received()

        logger.info("Handshake Complete!")

        await self.send_select_control_type()

        logger.info("Starting tests!")

        await self.execute_test_suite()

        logger.info(self.report.generate_certificate_dict())

        logger.info("Exiting Main Loop.")

    async def send_select_control_type(self):
        # TODO: Select the control type in a better way.
        logger.info("Selecting Control Type.")
        if (
            self.controller.resource_manager_details is None
            or self.controller.resource_manager_details.available_control_types is None
        ):
            raise Exception("Missing Resource Details.")

        if self.channel is None:
            raise ValueError("Channel not set.")

        control_type = None

        while (
            control_type is None
            and len(self.controller.resource_manager_details.available_control_types)
            > 0
        ):
            control_type = (
                self.controller.resource_manager_details.available_control_types.pop()
            )
            if control_type in self.controllers:
                break
            # logger.info(
            #     "Getting controller %s from %s", control_type, self.controllers
            # )

        if control_type is None:
            logger.warning("No suitable control types available. Exiting...")
            await self.stop()
            return

        logger.info("Selecting control type %s", control_type)
        self.set_control_type(control_type)

        await self.controller.select_control_type(self.channel)

    async def setup(self, channel: S2Channel, *args, **kwargs):
        await super().setup()
        self.channel = channel

        self._handshake_complete = asyncio.Event()

        self.create_task(self.main_loop(), True)

        self.create_task(self.channel.run(), True)
        self.create_task(self.process_received_messages(), True)

    async def cleanup(self, *args, **kwargs):
        await super().cleanup()

        if self.channel is not None:
            await self.channel.stop()

    async def run(self, *args, **kwargs):
        self.running = True

        await self.setup(*args, **kwargs)

        await self._stop_event.wait()

        await self.cleanup(*args, **kwargs)

        self.running = False


def create_controllers_dict_with_config(
    config: Config,
) -> Dict[ProtocolControlType, Controller]:
    controllers: Dict[ProtocolControlType, Controller] = {}

    controllers[ProtocolControlType.NO_SELECTION] = BaseController()

    if config.control_types.frbc and config.control_types.frbc.enabled:
        controllers[ProtocolControlType.FILL_RATE_BASED_CONTROL] = FRBCController()

    if config.control_types.pebc and config.control_types.pebc.enabled:
        controllers[ProtocolControlType.POWER_ENVELOPE_BASED_CONTROL] = PEBCController()

    return controllers


def create_test_executor(config: Config) -> IntegrationTestExecutor:
    report = ComplianceReport(timestamp=datetime.now())

    controllers = create_controllers_dict_with_config(config)

    test_suite = (
        TestSuiteBuilder(config.control_types, report)
        .with_test_case(PEBCTestCase)
        .with_test_case(FRBCTestCase)
        .build()
    )

    executor = IntegrationTestExecutor(
        available_control_types=controllers, test_suite=test_suite, report=report
    )

    return executor
