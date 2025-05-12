import abc
import asyncio
from datetime import datetime
import logging
from typing import Dict, Optional

from s2python.common import ControlType as ProtocolControlType
from s2python.message import S2Message


from testsuites.certificate.certificate import ComplianceReport
from testsuites.test_suite.test_suite import TestSuite, TestSuiteBuilder
from testsuites.test_suite import (
    FRBCTestCase,
    ReceivePowerMeasurementTestCase,
    ReceivePowerForecastTestCase,
)
from testsuites.test_suite.pebc_test_cases import (
    PEBCCurtailmentInstructionTestCase,
    PEBCPowerConstraintsTestCase,
)
from testsuites.controllers import (
    Controller,
    BaseController,
    PEBCController,
    FRBCController,
)


from connectivity.async_task_manager import AsyncTaskManager
from connectivity.s2_channel import S2Channel
from connectivity.config import Config
from connectivity.connection_adapter import ConnectionClosed, ConnectionError


logger = logging.getLogger(__name__)


class AbstractExecutor(abc.ABC):

    report: Optional[ComplianceReport] = None

    _stop_event: asyncio.Event

    running = False

    def is_running(self):
        return self.running

    @abc.abstractmethod
    async def run(self, *args, **kwargs):
        pass


class IntegrationTestExecutor(AbstractExecutor):

    # The channel which connects to the S2 RM.
    channel: Optional["S2Channel"] = None

    controller: Controller
    controllers: Dict[ProtocolControlType, Controller]

    test_suite: TestSuite

    report: ComplianceReport

    _stop_event: asyncio.Event
    _handshake_complete: asyncio.Event

    logger: logging.Logger

    def __init__(
        self,
        available_control_types: Dict[ProtocolControlType, Controller],
        test_suite: TestSuite,
        report: ComplianceReport,
        logger: logging.Logger = logging.getLogger(__name__),
    ) -> None:

        self.controllers = available_control_types

        controller = available_control_types.get(ProtocolControlType.NO_SELECTION)
        if controller is None:
            raise ValueError("A NO_SELECTION controller must be provided.")
        self.controller = controller

        self.test_suite = test_suite

        self.report = report

        self.logger = logger

        self._stop_event = asyncio.Event()
        self._handshake_complete = asyncio.Event()

        self.running = False

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

                # logger.info(message)
                await self.process_message(message)
        except asyncio.CancelledError:
            self.logger.info("Message Channel cancelled.")
        except ConnectionClosed:
            pass
        except Exception as e:
            self.logger.exception("Message processor encountered an error: %s", e)
            await self.stop()

    async def execute_test_suite(self):
        # Wait until the handshake is complete before starting the testing.
        # TODO: Figure out how to include the handshake process in the testing.

        if self.channel is None:
            raise ValueError("Channel not set.")

        if self.controller:
            await self.test_suite.execute(self.channel, self.controller)

    async def main_loop(self):
        self.logger.info("Starting Main Loop.")
        if self.channel is None:
            raise ValueError("Channel not set.")

        try:
            await self.controller.perform_handshake(self.channel)

            await self.controller.wait_until_rm_details_received()

            self.logger.info("Handshake Complete!")

            await self.send_select_control_type()

            self.logger.info("Starting tests!")

            await self.execute_test_suite()

            self.logger.info("Sending graceful disconnect.")
            await self.controller.perform_disconnect(self.channel)

            self.logger.info("Exiting Main Loop.")
        except asyncio.CancelledError:
            self.logger.warning("Main loop was cancelled.")
            raise  # Propagate for TaskGroup
        except Exception as e:
            self.logger.exception("Exception in main_loop: %s", e)
            await self.stop()
            raise
        finally:
            self.logger.info("Main loop finished. Signaling stop.")
            await self.stop()

    async def send_select_control_type(self):
        # TODO: Select the control type in a better way.
        self.logger.info("Selecting Control Type.")
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
            self.logger.warning("No suitable control types available. Exiting...")
            await self.stop()
            return

        self.logger.info("Selecting control type %s", control_type)
        self.set_control_type(control_type)

        await self.controller.select_control_type(self.channel)

    def is_running(self):
        return self.running

    async def stop(self):
        self.logger.debug("Stop Called in class %s", self.__class__.__name__)
        self._stop_event.set()

        if self.channel is not None:
            await self.channel.stop()

    async def setup(self, channel: S2Channel, *args, **kwargs):
        self.channel = channel

        self._stop_event.clear()
        self._handshake_complete.clear()

        # self.create_task(self.main_loop(), True)

        # self.create_task(self.channel.run(), True)
        # self.create_task(self.process_received_messages(), True)

    async def cleanup(self, *args, **kwargs):
        pass

    async def run_channel(self):
        if self.channel is None:
            raise ValueError("S2 Channel is ot provided")
        try:
            await self.channel.run()
        except ConnectionClosed:
            await self.stop()
        except ConnectionError:
            await self.stop()

    async def run(self, *args, **kwargs):
        self.running = True
        await self.setup(*args, **kwargs)

        try:
            async with asyncio.TaskGroup() as tg:

                if self.channel is None:
                    self.logger.error(
                        "Channel not initialized before run, cannot start channel.run task."
                    )
                    await self.stop()
                    self.running = False
                    return

                # TODO: Should this use `run_channel()`?
                tg.create_task(self.channel.run(), name="ChannelRun")
                tg.create_task(self.process_received_messages(), name="MessageProcess")
                tg.create_task(self.main_loop(), name="MainLoop")

                self.logger.info(
                    "IntegrationTestExecutor TaskGroup completed successfully."
                )

        except* Exception as eg:  # Catches one or more exceptions from tasks
            self.logger.error(
                f"ExceptionGroup caught in IntegrationTestExecutor run: {len(eg.exceptions)} exceptions"
            )
            for i, exc in enumerate(eg.exceptions):
                self.logger.error(
                    f"  Exception {i+1}/{len(eg.exceptions)} in TaskGroup:",
                    exc_info=exc,
                )
            await self.stop()  # Signal cooperative shutdown for other parts if any
        # except asyncio.CancelledError:
        #     logger.warning("IntegrationTestExecutor run method was cancelled externally.")
        #     self.stop()
        finally:
            self.logger.info("IntegrationTestExecutor run method finishing.")
            await self.cleanup()  # Perform final cleanup (e.g., channel.stop())
            self.logger.info("Cleanup finished.")
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


def create_test_executor(
    config: Config, logger: logging.Logger
) -> IntegrationTestExecutor:
    report = ComplianceReport(timestamp=datetime.now(), device=config.device_details)

    controllers = create_controllers_dict_with_config(config)

    test_suite = (
        TestSuiteBuilder(config.control_types, report)
        .with_test_case(ReceivePowerForecastTestCase)
        .with_test_case(ReceivePowerMeasurementTestCase)
        .with_test_case(PEBCPowerConstraintsTestCase)
        .with_test_case(PEBCCurtailmentInstructionTestCase)
        .with_test_case(FRBCTestCase)
        .build()
    )

    executor = IntegrationTestExecutor(
        available_control_types=controllers,
        test_suite=test_suite,
        report=report,
        logger=logger,
    )

    return executor
