import abc
import asyncio
from datetime import datetime
import logging
from typing import Callable, Dict, Optional
import uuid

from s2python.common import (
    ControlType as ProtocolControlType,
    EnergyManagementRole,
    Handshake,
    ResourceManagerDetails,
    CommodityQuantity,
    Currency,
    Duration,
    Role,
    RoleType,
    Commodity,
    SelectControlType,
)
from s2python.message import S2Message


from testsuites.message_handlers import send_okay_message
from testsuites.util import wait_for_event_or_stop
from testsuites.certificate.certificate import ComplianceReport
from testsuites.test_suite.test_suite import TestSuite, TestSuiteBuilder
from testsuites.test_logger import TestLogger
from testsuites.test_suite import (
    ReceivePowerMeasurementTestCase,
    ReceivePowerForecastTestCase,
)
from testsuites.test_logger import (
    AbstractTestLogger,
    TestLogger,
    ServerTestLogger,
    TestLoggerLevel,
)
from testsuites.test_suite.pebc_test_cases import (
    PEBCCurtailmentInstructionTestCase,
    PEBCPowerConstraintsTestCase,
)
from testsuites.controllers import (
    Controller,
    BaseRMController,
    BaseCEMController,
    PEBCRMController,
    FRBCRMController,
)
from testsuites.test_suite.frbc_test_cases import (
    FRBCActuatorStatusTestCase,
    FRBCSystemDescriptionTestCase,
    FRBCStorageStatusTestCase,
    FRBCUsageForecastTestCase,
)


from connectivity.s2_channel import S2Channel
from connectivity.config import (
    Config,
    ControlTypeRMTestConfig,
    ControlTypeCEMTestConfig,
)
from connectivity.connection_adapter import ConnectionClosed, ConnectionError


logger = logging.getLogger(__name__)


class AbstractExecutor(abc.ABC):

    _stop_event: asyncio.Event

    running = False

    def is_running(self):
        return self.running

    @abc.abstractmethod
    async def run(self, *args, **kwargs):
        pass


class AbstractRoleExecutor(abc.ABC):
    # In the role executor the channel is only used for sending messages. Receiving messages handled by IntegrationTestExecutor.
    channel: Optional["S2Channel"] = None
    role: EnergyManagementRole

    controller: Controller
    controllers: Dict[ProtocolControlType, Controller]

    test_suite: TestSuite

    report: ComplianceReport
    test_logger: AbstractTestLogger

    _main_loop_started_event: asyncio.Event

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

    async def run(self, channel: S2Channel, *args, **kwargs):
        self.channel = channel

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


class RMTestExecutor(AbstractRoleExecutor):
    role = EnergyManagementRole.RM
    controller: BaseRMController

    async def execute_test_suite(self):
        # Wait until the handshake is complete before starting the testing.
        # TODO: Figure out how to include the handshake process in the testing.

        if self.channel is None:
            raise ValueError("Channel not set.")

        if self.controller:
            await self.test_suite.execute(self.channel, self.controller, self.role)

    async def main_loop(self):
        await super().main_loop()
        logger.info("Starting Main Loop for RM Test Executor.")
        if self.channel is None:
            raise ValueError("Channel not set.")

        self.test_logger.info("Test suite starting. ", ident=0)
        try:
            await self.controller.perform_handshake(self.channel)

            await self.controller.wait_until_rm_details_received()

            self.test_logger.success("Handshake Complete", ident=0)

            await self.send_select_control_type()

            await self.execute_test_suite()

            await self.controller.perform_disconnect(self.channel)
            self.test_logger.success("Sent Graceful Disconnect..", ident=0)

            logger.info("Exiting Test Executor Main Loop.")
        except asyncio.CancelledError:
            logger.warning("Main loop was cancelled.")
            raise  # Propagate for TaskGroup
        except Exception as e:
            logger.exception("Exception in main_loop: %s", e)
            raise
        finally:
            self.test_logger.info("Main loop finished. Signaling stop.", ident=0)

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
            self.test_logger.error(
                "Select Control Type Failed. No suitable control type available.",
                ident=0,
            )
            raise Exception("No suitable control types available.")

        self.set_control_type(control_type)

        await self.controller.select_control_type(self.channel)

        self.test_logger.success(f"Control Type Selection. Selected: {control_type}")


class CEMTestExecutor(AbstractRoleExecutor):
    role = EnergyManagementRole.CEM
    controller: BaseCEMController

    async def handle_select_control_type(self, message: SelectControlType):
        control_type = message.control_type

        try:
            self.set_control_type(control_type)
        except KeyError:
            raise ValueError("Invalid control type selection...")

    async def process_message(self, message: S2Message):
        if type(message) == SelectControlType:
            await self.handle_select_control_type(message)
        return super().process_message(message)

    async def main_loop(self):
        logger.info("Starting Main Loop for CEM Test Executor.")

        if self.channel is None:
            raise ValueError("Channel not set.")

        self.test_logger.info("Test suite starting. ", ident=0)

        await self.controller.perform_handshake(self.channel)


class IntegrationTestExecutor(AbstractExecutor):
    """
    Waits for a handshake message to be received and based on the Role value chooses the correct
    RoleExecutor. From that point onwards all messages are passed straight to the role executor.
    The main method of the role executor is executed.
    """

    # The channel which connects to the S2 RM.
    channel: Optional["S2Channel"] = None

    executor: AbstractRoleExecutor | None = None
    role_executors: Dict[EnergyManagementRole, AbstractRoleExecutor]

    _stop_event: asyncio.Event

    _select_role_executor = asyncio.Event()

    def __init__(
        self,
        role_executors: Dict[EnergyManagementRole, AbstractRoleExecutor],
    ) -> None:

        self.role_executors = role_executors

        self._stop_event = asyncio.Event()
        self._select_role_executor = asyncio.Event()

        self.running = False

    async def handle_handshake(self, message: Handshake):
        # On handshake we select the executor based on the role of the connected device.
        role = message.role

        self.executor = self.role_executors[role]

        # Setting this will allow the main_loop to proceed
        self._select_role_executor.set()

    async def process_message(self, message: S2Message):

        if type(message) == Handshake:
            await self.handle_handshake(message)

        # Handle the incoming message with the selected executor
        if self.executor is not None:
            await self.executor.process_message(message)
        else:
            raise ValueError(
                f"Message of type {message.message_type} received before Handshake."
            )

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
            logger.info("Message Channel cancelled.")
        except ConnectionClosed:
            pass
        except Exception as e:
            logger.exception("Message processor encountered an error: %s", e)
            await self.stop()

    def is_running(self):
        return self.running

    async def stop(self):
        logger.debug("Stop Called in class %s", self.__class__.__name__)
        self._stop_event.set()

        if self.channel is not None:
            await self.channel.stop()

    async def setup(self, channel: S2Channel, *args, **kwargs):
        self.channel = channel

        self._stop_event.clear()
        self._select_role_executor.clear()

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

    async def main_loop(self):
        # Wait until the initial handshake message has been received to set role executor.
        await wait_for_event_or_stop(self._select_role_executor, self._stop_event)

        if self.executor is not None and self.channel is not None:
            await self.executor.run(self.channel)
        else:
            raise ValueError("Unable to run role executor main loop.")

        await self.stop()

    async def run(self, *args, **kwargs):
        self.running = True
        await self.setup(*args, **kwargs)

        try:
            async with asyncio.TaskGroup() as tg:

                if self.channel is None:
                    logger.error(
                        "Channel not initialized before run, cannot start channel.run task."
                    )
                    await self.stop()
                    self.running = False
                    return

                tg.create_task(self.run_channel(), name="ChannelRun")
                tg.create_task(self.process_received_messages(), name="MessageProcess")
                tg.create_task(self.main_loop(), name="MainLoop")

                logger.info("IntegrationTestExecutor TaskGroup completed successfully.")

        except* Exception as eg:  # Catches one or more exceptions from tasks
            logger.error(
                f"ExceptionGroup caught in IntegrationTestExecutor run: {len(eg.exceptions)} exceptions"
            )
            for i, exc in enumerate(eg.exceptions):
                logger.error(
                    f"  Exception {i+1}/{len(eg.exceptions)} in TaskGroup:",
                    exc_info=exc,
                )
            await self.stop()  # Signal cooperative shutdown for other parts if any
        # except asyncio.CancelledError:
        #     logger.warning("IntegrationTestExecutor run method was cancelled externally.")
        #     self.stop()
        finally:
            logger.info("IntegrationTestExecutor run method finishing.")
            await self.cleanup()  # Perform final cleanup (e.g., channel.stop())
            logger.info("Cleanup finished.")
            self.running = False

    async def get_compliance_report(self) -> ComplianceReport:
        if self.executor is not None:
            return self.executor.report
        raise ValueError("No testing has been done.")


def create_rm_controllers_dict_with_config(
    config: ControlTypeRMTestConfig,
) -> Dict[ProtocolControlType, Controller]:
    controllers: Dict[ProtocolControlType, Controller] = {}

    controllers[ProtocolControlType.NO_SELECTION] = BaseRMController()

    if config.frbc and config.frbc.enabled:
        controllers[ProtocolControlType.FILL_RATE_BASED_CONTROL] = FRBCRMController()

    if config.pebc and config.pebc.enabled:
        controllers[ProtocolControlType.POWER_ENVELOPE_BASED_CONTROL] = (
            PEBCRMController()
        )

    return controllers


def create_cem_controllers_dict_with_config(
    config: ControlTypeCEMTestConfig,
) -> Dict[ProtocolControlType, Controller]:
    controllers: Dict[ProtocolControlType, Controller] = {}

    controllers[ProtocolControlType.NO_SELECTION] = BaseCEMController(
        # TODO: More details should come from config.
        ResourceManagerDetails(
            available_control_types=config.get_enabled_control_types(),
            roles=[
                Role(
                    role=RoleType.ENERGY_PRODUCER,
                    commodity=Commodity.ELECTRICITY,
                )
            ],
            name="TEST RM",
            manufacturer="TEST",
            model="TEST",
            firmware_version="0",
            currency=Currency.EUR,
            message_id=uuid.uuid4(),
            provides_forecast=True,
            provides_power_measurement_types=[CommodityQuantity.ELECTRIC_POWER_L1],
            resource_id=uuid.uuid4(),
            serial_number="00000",
            instruction_processing_delay=Duration(0),
        )
    )

    return controllers


def create_test_executor(
    config: Config, test_logger: AbstractTestLogger
) -> IntegrationTestExecutor:
    report = ComplianceReport(timestamp=datetime.now(), device=config.device_details)

    rm_controllers = create_rm_controllers_dict_with_config(config.roles.rm)
    rm_test_suite = (
        TestSuiteBuilder(config.roles, report, test_logger)
        # Not Controllable Test Cases
        .with_test_case(ReceivePowerForecastTestCase)
        .with_test_case(ReceivePowerMeasurementTestCase)
        # PEBC Test Cases
        .with_test_case(PEBCPowerConstraintsTestCase)
        .with_test_case(PEBCCurtailmentInstructionTestCase)
        # FRBC Test Cases
        .with_test_case(FRBCUsageForecastTestCase)
        .with_test_case(FRBCActuatorStatusTestCase)
        .with_test_case(FRBCSystemDescriptionTestCase)
        .with_test_case(FRBCStorageStatusTestCase)
        .build()
    )
    rm_role_executor = RMTestExecutor(
        available_control_types=rm_controllers,
        test_suite=rm_test_suite,
        report=report,
        test_logger=test_logger,
    )

    cem_controllers = create_cem_controllers_dict_with_config(config.roles.cem)
    cem_test_suite = TestSuiteBuilder(config.roles, report, test_logger).build()
    cem_role_executor = CEMTestExecutor(
        available_control_types=cem_controllers,
        test_suite=cem_test_suite,
        report=report,
        test_logger=test_logger,
    )

    role_executors: Dict[EnergyManagementRole, AbstractRoleExecutor] = {
        EnergyManagementRole.RM: rm_role_executor,
        EnergyManagementRole.CEM: cem_role_executor,
    }

    executor = IntegrationTestExecutor(role_executors=role_executors)

    return executor
