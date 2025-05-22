import logging
import abc
import asyncio
from datetime import datetime
import logging
import time
from typing import Dict, Optional
import uuid

from s2python.common import (
    ControlType as ProtocolControlType,
    EnergyManagementRole,
    ResourceManagerDetails,
)
from s2python.message import S2Message


from testsuites.certificate.certificate import (
    TestResult,
    TestResultStatus,
    TestSuiteResults,
)
from testsuites.controllers import (
    BaseRMController,
)
from .base_role_executor import (
    AbstractRoleExecutor,
    ExitMainLoopException,
    execute_as_test,
)

logger = logging.getLogger(__name__)


class RMTestExecutor(AbstractRoleExecutor):
    role = EnergyManagementRole.RM
    controller: BaseRMController

    available_control_types: set[ProtocolControlType] = set()
    tested_control_types: set[ProtocolControlType] = set()

    async def main_loop(self):
        await super().main_loop()
        logger.info("Starting Main Loop for RM Test Executor.")
        if self.channel is None:
            raise ValueError("Channel not set.")

        self.test_logger.info("Test suite starting. ", ident=0)
        try:
            await self.send_handshake()
            await self.wait_for_handshake()

            await self.wait_for_rm_details()

            for control_type in self.available_control_types:

                await self.send_select_control_type(control_type)

                await self.execute_test_suite()

            await self.controller.send_session_request_disconnect(self.channel)
            self.test_logger.success("Sent Graceful Disconnect.", ident=0)

            logger.info("Exiting Test Executor Main Loop.")
        except asyncio.CancelledError:
            logger.warning("Main loop was cancelled.")
            raise  # Propagate for TaskGroup
        except Exception as e:
            logger.exception("Exception in main_loop: %s", e)
            raise
        finally:
            self.test_logger.info("Main loop finished. Signaling stop.", ident=0)

    @execute_as_test(
        test_name="9.2.1. Update Resource Manager Details",
        error_message_prefix="Error whilst waiting for RM Details:",
    )
    async def wait_for_rm_details(self):
        resource_manager_details = (
            await self.controller.wait_until_rm_details_received()
        )
        for control_type in resource_manager_details.available_control_types:
            self.available_control_types.add(control_type)

        self.test_logger.success("Resource Manager Details Received.", ident=0)

    async def send_select_control_type(self, control_type: ProtocolControlType):
        if self.controller.control_type != ProtocolControlType.NO_SELECTION:
            await self.update_active_control_type(control_type)
        else:
            await self.activate_control_type(control_type)

    @execute_as_test(
        test_name="9.2.2. Activate Control Type",
        error_message_prefix="Failed to activate control type",
    )
    async def activate_control_type(self, control_type: ProtocolControlType):
        # Test case for setting the initial control type
        if self.channel is None:
            raise ValueError("Channel not set.")

        self.set_control_type(control_type)
        await self.controller.send_select_control_type(self.channel)
        self.test_logger.success(f"Control Type Set to {control_type.name}", ident=0)

    @execute_as_test(
        test_name="9.2.3. Update Active Control Type",
        error_message_prefix="Failed to activate control type",
    )
    async def update_active_control_type(self, control_type: ProtocolControlType):
        # Test case for changing the control type after one has already been set
        if self.channel is None:
            raise ValueError("Channel not set.")

        self.set_control_type(control_type)
        await self.controller.send_select_control_type(self.channel)
        self.test_logger.success(f"Control Type Set to {control_type.name}", ident=0)

    # async def send_select_control_type(self):
    #     # TODO: Select the control type in a better way.
    #     try:
    #         logger.info("Selecting Control Type.")
    #         if (
    #             self.controller.resource_manager_details is None
    #             or self.controller.resource_manager_details.available_control_types
    #             is None
    #         ):
    #             raise Exception("Missing Resource Details.")

    #         if self.channel is None:
    #             raise ValueError("Channel not set.")

    #         control_type = None

    #         while (
    #             control_type is None
    #             and len(
    #                 self.controller.resource_manager_details.available_control_types
    #             )
    #             > 0
    #         ):
    #             control_type = (
    #                 self.controller.resource_manager_details.available_control_types.pop()
    #             )
    #             if control_type in self.controllers:
    #                 break
    #             # logger.info(
    #             #     "Getting controller %s from %s", control_type, self.controllers
    #             # )

    #         if control_type is None:
    #             raise Exception(
    #                 "Select Control Type Failed. No suitable control type available.",
    #             )

    #         self.set_control_type(control_type)

    #         await self.controller.send_select_control_type(self.channel)

    #         self.test_logger.success(
    #             f"Control Type Selection. Selected: {control_type}", ident=0
    #         )
    #     except asyncio.CancelledError:
    #         raise
    #     except Exception as e:
    #         self.test_logger.error(f"Failed to select Control Type: {e}")
