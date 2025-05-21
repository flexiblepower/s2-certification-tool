import abc
import asyncio
from datetime import datetime
import logging
from typing import Dict, Optional
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


from testsuites.util import wait_for_event_or_stop
from testsuites.certificate.certificate import ComplianceReport
from testsuites.test_suite import (
    TestSuiteBuilder,
    build_rm_test_suite,
    build_cem_test_suite,
)
from testsuites.test_logger import (
    AbstractTestLogger,
)
from testsuites.controllers import (
    Controller,
    BaseRMController,
    BaseCEMController,
    PEBCRMController,
    FRBCRMController,
    FRBCCEMCOntroller,
)


from connectivity.s2_channel import S2Channel
from connectivity.config import (
    Config,
    ControlTypeRMTestConfig,
    ControlTypeCEMTestConfig,
)
from connectivity.connection_adapter import ConnectionClosed, ConnectionError
from .role_executors import AbstractRoleExecutor, CEMTestExecutor, RMTestExecutor


logger = logging.getLogger(__name__)


class AbstractExecutor(abc.ABC):

    _stop_event: asyncio.Event

    running = False

    def is_running(self):
        return self.running

    @abc.abstractmethod
    async def run(self, *args, **kwargs):
        pass


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
            # logger.info("Passing message to executor: %s", message)
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
            raise ValueError("S2 Channel is not provided")
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
            logger.info("Choosing executor as role %s", self.executor.role)
            # await wait_for_event_or_stop(self._select_role_executor, self._stop_event)
            await self.executor.run(self.channel, self._stop_event)
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

    # TODO: More details should come from config.
    rm_details = ResourceManagerDetails(
        available_control_types=[
            ProtocolControlType.NOT_CONTROLABLE
        ],  # I'll set this based on the controllers dict
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

    controllers[ProtocolControlType.NO_SELECTION] = BaseCEMController(rm_details)
    controllers[ProtocolControlType.FILL_RATE_BASED_CONTROL] = FRBCCEMCOntroller(
        rm_details
    )

    control_type_set = set(controllers.keys())
    control_type_set.discard(ProtocolControlType.NO_SELECTION)
    rm_details.available_control_types = list(control_type_set)

    return controllers


def create_test_executor(
    config: Config, test_logger: AbstractTestLogger
) -> IntegrationTestExecutor:
    report = ComplianceReport(timestamp=datetime.now(), device=config.device_details)

    rm_controllers = create_rm_controllers_dict_with_config(config.roles.rm)
    rm_test_suite_builder = build_rm_test_suite(config, report, test_logger)
    rm_role_executor = RMTestExecutor(
        available_control_types=rm_controllers,
        test_suite=rm_test_suite_builder.build(),
        report=report,
        test_logger=test_logger,
    )

    cem_controllers = create_cem_controllers_dict_with_config(config.roles.cem)
    cem_test_suite_builder = build_cem_test_suite(config, report, test_logger)
    cem_role_executor = CEMTestExecutor(
        available_control_types=cem_controllers,
        test_suite=cem_test_suite_builder.build(),
        report=report,
        test_logger=test_logger,
    )

    role_executors: Dict[EnergyManagementRole, AbstractRoleExecutor] = {
        EnergyManagementRole.RM: rm_role_executor,
        EnergyManagementRole.CEM: cem_role_executor,
    }

    executor = IntegrationTestExecutor(role_executors=role_executors)

    return executor
