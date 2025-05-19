import logging
import abc
import asyncio
from datetime import datetime
import logging
from typing import Dict, Optional
import uuid

from s2python.common import (
    ControlType as ProtocolControlType,
    EnergyManagementRole,
)
from s2python.message import S2Message


from testsuites.controllers import (
    BaseRMController,
)
from .base import AbstractRoleExecutor

logger = logging.getLogger(__name__)


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
