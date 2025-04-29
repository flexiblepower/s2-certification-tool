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


from connection import Connection
from s2testing.connection import SendOkay
from s2testing.controllers import Controller
from s2testing.test_suite.test_suite import TestSuite
from s2testing.util import wait_for_event_or_stop

logger = logging.getLogger(__name__)


class IntegrationTestOrchestrator:
    role: EnergyManagementRole = EnergyManagementRole.CEM

    connection: Optional["Connection"] = None

    resource_manager_details: Optional[ResourceManagerDetails] = None

    controller: Controller
    controllers: Dict[ProtocolControlType, Controller]

    _tasks = set()

    # When set the main loop of Connection will trigger the stopping of all `_tasks`
    _stop_event: asyncio.Event

    # The functions which handle the Handshake messages. All other messages should be handled by the controllers.
    handshake_message_handlers: Dict[
        Type[S2Message], Callable[[S2Message, Awaitable[None]], CoroutineType]
    ]

    test_suite: TestSuite

    running = False

    def __init__(
        self,
        available_control_types: Dict[ProtocolControlType, Controller],
        test_suite: TestSuite,
        report: ComplianceReport,
    ) -> None:  # pylint: disable=too-many-arguments

        self.controllers = available_control_types

        controller = available_control_types.get(ProtocolControlType.NO_SELECTION)
        if controller is None:
            raise ValueError("A NO_SELECTION controller must be provided.")
        self.controller = controller

        self.test_suite = test_suite

        self.handshake_message_handlers = {  # type: ignore
            Handshake: self.handle_handshake,
            ResourceManagerDetails: self.handle_rm_details,
        }

        self._stop_event = asyncio.Event()

        self.report = report

    def set_control_type(self, control_type: ProtocolControlType):
        controller = self.controllers[control_type]
        # Put the RM Details into the new controller.
        controller.resource_manager_details = controller.resource_manager_details
        self.controller = controller

    async def process_received_messages(self):
        """AsyncIO task which pops messages off the queue and processes them using the control type."""

        if self.connection is None:
            raise ValueError("Connection not set.")

        try:
            while not self._stop_event.is_set():
                try:
                    # Use a timeout to periodically check for cancellation
                    msg: S2Message = await asyncio.wait_for(
                        self.connection.get_next_message(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue  # Check stop event and loop again

                # If Handshake message then use the handshake message handlers
                if type(msg) in self.handshake_message_handlers:
                    send_okay = SendOkay(self.connection, msg.message_id)  # type: ignore
                    await self.handshake_message_handlers[type(msg)](
                        msg, send_okay.run_async()
                    )
                    await send_okay.ensure_send_async(type(msg))
                elif self.controller is not None:
                    await self.controller.handle_message(msg, self.connection)  # type: ignore
                else:
                    logger.warning("No handler available for %s", msg.message_type)

        except asyncio.CancelledError:
            logger.info("Message receiver cancelled.")
        except Exception as e:
            logger.exception("Message processor encountered an error: %s", e)
        finally:
            self._stop_event.set()

    async def execute_test_suite(self):
        # Wait until the handshake is complete before starting the testing.
        # TODO: Figure out how to include the handshake process in the testing.

        if self.connection is None:
            raise ValueError("Connection not set.")

        if self.controller:
            await self.test_suite.execute(self.connection, self.controller)

    async def main_loop(self):
        await self.initiate_handshake()

        if not await wait_for_event_or_stop(self._handshake_complete, self._stop_event):
            return

        logger.info("Handshake Complete!")

        await self.send_select_control_type()

        logger.info("Starting tests!")

        await self.execute_test_suite()

        logger.info(self.report.generate_certificate_dict())

    async def connection_receive_messages(self):
        """Wrapping the receive messages method to allow catching of validation errors."""

        if self.connection is None:
            raise ValueError("Connection not set.")

        try:
            await self.connection.receive_messages()
        except S2ValidationError as e:
            if self.controller is not None:
                self.controller.handle_s2_validation_exception(e)
            else:
                logger.error("S2 Validation Error encountered: %s", e)
        except:
            logger.exception("An error occurred whilst receiving messages.")

    async def task_wrapper(self, task: Coroutine, stop_on_complete):
        """Uncaught exceptions don't get logged reliably in tasks. This catches all exceptions to log them and kill the controller.

        TODO: Maybe handle the exceptions in a better way...
        """
        try:
            await task
            if stop_on_complete:
                self.stop()
        except:
            logger.exception("Exception in task!")
            self.stop()

    def create_task(self, task: Coroutine, stop_on_complete=False):
        self._tasks.add(asyncio.create_task(self.task_wrapper(task, stop_on_complete)))

    async def run(self, connection: Connection):
        self.running = True
        self.connection = connection

        self._handshake_complete = asyncio.Event()
        self._stop_event = asyncio.Event()

        # Receives messages and puts them onto the queue.
        self.create_task(self.connection_receive_messages(), True)
        self.create_task(self.process_received_messages(), True)
        self.create_task(self.main_loop(), True)

        await self._stop_event.wait()

        for task in self._tasks:
            task.cancel()

        await self.connection.stop()

        await asyncio.gather(*self._tasks)

        self._tasks.clear()

        self.running = False

    def stop(self):
        self._stop_event.set()

    def is_running(self):
        return self.running

    async def initiate_handshake(self):
        if self.connection is None:
            raise ValueError("Connection not set.")

        await self.connection.send_msg_and_await_reception_status(
            Handshake(
                message_id=uuid.uuid4(),  # type: ignore
                role=self.role,
                supported_protocol_versions=[S2_VERSION],
            )
        )

        self.controller.handshake_acknowledged()

    async def handle_handshake(
        self,
        message: Handshake,
        send_okay: Awaitable[None],
    ) -> None:

        if self.connection is None:
            raise ValueError("Connection not set.")

        logger.debug(
            "%s supports S2 protocol versions: %s",
            message.role,
            message.supported_protocol_versions,
        )
        if message.supported_protocol_versions is None:
            raise ValueError(
                "Missing supported protocol versions in handshake message."
            )

        await send_okay

        await self.connection.send_msg_and_await_reception_status(
            HandshakeResponse(
                message_id=uuid.uuid4(),
                selected_protocol_version=message.supported_protocol_versions[0],
            )
        )

        self.controller.handshake_received()

    async def send_select_control_type(self):
        # TODO: Select the control type in a better way.
        logger.info("Selecting Control Type.")
        if (
            self.resource_manager_details is None
            or self.resource_manager_details.available_control_types is None
        ):
            raise Exception("Missing Resource Details.")

        if self.connection is None:
            raise ValueError("Connection not set.")

        controller: Optional[Controller] = None

        while (
            controller is None
            and len(self.resource_manager_details.available_control_types) > 0
        ):
            control_type = self.resource_manager_details.available_control_types.pop()
            if control_type in self.controllers:
                # logger.info(
                #     "Getting controller %s from %s", control_type, self.controllers
                # )
                controller = self.controllers[control_type]

        if controller is None:
            logger.warning("No suitable control types available. Exiting...")
            self.stop()
            return

        logger.info("Selecting control type %s", controller)

        self.set_control_type(controller.control_type)

        await self.connection.send_msg_and_await_reception_status(
            SelectControlType(
                message_id=uuid.uuid4(), control_type=controller.control_type
            )
        )

    async def handle_rm_details(
        self,
        message: ResourceManagerDetails,
        send_okay: Awaitable[None],
    ):

        self.resource_manager_details = message

        if self.connection is None:
            raise ValueError("Connection not set.")

        # Pass it to the no selection controller to use it as part of the test cases.
        await self.controller.handle_message(message, self.connection, send_okay)

        self._handshake_complete.set()
