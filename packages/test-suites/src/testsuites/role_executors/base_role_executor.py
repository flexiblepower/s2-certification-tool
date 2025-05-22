import abc
import asyncio
import functools
import logging
import time
from typing import Any, Callable, Coroutine, Dict, Optional, ParamSpec, TypeVar

from s2python.common import (
    ControlType as ProtocolControlType,
    EnergyManagementRole,
)
from s2python.message import S2Message


from testsuites.certificate.certificate import (
    ComplianceReport,
    TestResult,
    TestResultStatus,
    TestSuiteResults,
)
from testsuites.test_suite.test_suite import TestSuite, TestSuiteBuilder
from testsuites.test_logger import (
    AbstractTestLogger,
)
from testsuites.controllers import (
    Controller,
)
from connectivity.s2_channel import S2Channel
from testsuites.util import wait_for_event_or_stop


logger = logging.getLogger(__name__)


class ExitMainLoopException(Exception):
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
    generic_tasks_test_suite_result = TestSuiteResults(name="9.2. Generic Tasks")

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

    async def send_handshake(self):
        try:
            if self.channel is None:
                raise ValueError("Channel is not set.")
            await self.controller.send_handshake(self.channel)
            self.test_logger.success("Handshake Message Sent", ident=0)
        except asyncio.CancelledError:
            logger.warning("Main loop was cancelled.")
            raise  # Propagate for TaskGroup
        except Exception as e:
            self.test_logger.error(f"Sending Handshake Message Failed: {e}", ident=0)
            raise ExitMainLoopException("Handshake failed.")

    async def wait_for_handshake(self):
        try:
            await wait_for_event_or_stop(
                self.controller._handshake_received_event,
                self._stop_event,
                description="Handshake received event.",
            )
            self.test_logger.success("Handshake Received.", ident=0)
        except asyncio.CancelledError:
            logger.warning("Main loop was cancelled.")
            raise  # Propagate for TaskGroup
        except Exception as e:
            self.test_logger.error(f"No handshake received: {e}", ident=0)
            return

    @abc.abstractmethod
    async def main_loop(self):
        self._main_loop_started_event.set()
        self.report.add_test_suite_result(self.generic_tasks_test_suite_result)

    async def execute_test_suite(self):
        # Wait until the handshake is complete before starting the testing.

        if self.channel is None:
            raise ValueError("Channel not set.")

        if self.controller:
            await self.test_suite.execute(self.channel, self.controller, self.role)


P = ParamSpec("P")
R = TypeVar("R")


def execute_as_test(
    test_name: str,
    error_message_prefix: str,
    success_log_ident: int = 0,
    error_log_ident: int = 0,
):
    """
    Decorator to handle common test step logic including timing,
    result status, error handling, and reporting.
    """

    def decorator(
        func: Callable[P, Coroutine[Any, Any, R]],
    ) -> Callable[P, Coroutine[Any, Any, R | None]]:
        @functools.wraps(func)
        async def wrapper(
            self_obj: AbstractRoleExecutor, *args: P.args, **kwargs: P.kwargs
        ) -> R | None:
            start_time = time.time()
            status = TestResultStatus.FAIL
            message = None
            return_value = None

            try:
                # Execute the specific test logic
                return_value = await func(self_obj, *args, **kwargs)  # type: ignore

                # Pass if no errors while running test
                status = TestResultStatus.PASS
            except asyncio.CancelledError:
                # Propagate cancellation
                raise
            except ExitMainLoopException as e:
                # If the test logic itself raises ExitMainLoopException,
                # log it and ensure it's the message.
                self_obj.test_logger.error(
                    f"{error_message_prefix}: {e}", ident=error_log_ident
                )
                message = str(e)
                raise  # Re-raise to be caught by outer loops if necessary
            except Exception as e:
                self_obj.test_logger.error(
                    f"{error_message_prefix}: {e}", ident=error_log_ident
                )
                message = str(e)
                # Consistently raise ExitMainLoopException for other errors
                # to ensure the main loop exits as in the original code.
                raise ExitMainLoopException(f"{error_message_prefix}: {e}") from e
            finally:
                end_time = time.time()
                result = TestResult(
                    name=test_name,
                    message=message,
                    status=status,
                    duration=round(end_time - start_time, 2),
                )
                self_obj.generic_tasks_test_suite_result.add_test_result(result)

            return return_value  # Return the result of the original function if any

        return wrapper  # type: ignore

    return decorator
