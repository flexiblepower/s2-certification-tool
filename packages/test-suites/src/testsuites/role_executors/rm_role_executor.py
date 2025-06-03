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
    SelectControlType,
    ReceptionStatusValues,
)
from s2python.message import S2Message


from testsuites.controllers import (
    BaseRMController,
)
from .base_role_executor import (
    ExitMainLoopException,
    TestRoleExecutor,
    execute_as_test,
)

logger = logging.getLogger(__name__)


class RMTestExecutor(TestRoleExecutor):
    role = EnergyManagementRole.CEM
    controller: BaseRMController

    available_control_types: set[ProtocolControlType] = set()
    tested_control_types: set[ProtocolControlType] = set()

    async def main_loop(self):
        # This sets the main loop started event so that the message processing can start.
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

            await self.test_select_not_supported_control_type()

            await self.controller.send_session_request_disconnect(self.channel)
            self.test_logger.success("Sent Graceful Disconnect.", ident=0)

            logger.info("Exiting Test Executor Main Loop.")
        except asyncio.CancelledError:
            logger.warning("Main loop was cancelled.")
            raise  # Propagate for TaskGroup
        except ExitMainLoopException:
            pass
        except Exception as e:
            logger.exception("Exception in main_loop: %s", e)
            raise
        finally:
            self.test_logger.info("Main loop finished. Signaling stop.", ident=0)

    @execute_as_test(
        test_name="9.2.2. Activate Control Type - Not Available",
        error_message_prefix="Resource Manager accepted a control type that it doesn't support: ",
    )
    async def test_select_not_supported_control_type(self):
        if self.channel is None:
            raise ValueError("Channel not provided")

        # Get all the control types that the RM does not implement
        control_types = set([member for member in ProtocolControlType])
        not_available_control_types = control_types.difference(
            self.available_control_types
        )
        # Remove the no selection type since all RMs support it and it isn't explicitly part of available control types
        not_available_control_types.remove(ProtocolControlType.NO_SELECTION)
        not_available_control_types.remove(ProtocolControlType.NOT_CONTROLABLE)

        for control_type in not_available_control_types:
            reception_status = await self.channel.send_msg_and_await_reception_status(
                SelectControlType(message_id=uuid.uuid4(), control_type=control_type),
                raise_on_error=False,
            )

            # RM should reply with non-Ok reception status since it should reject the selected control type
            if reception_status.status == ReceptionStatusValues.OK:
                raise AssertionError(
                    f"RM Accepted selection of control type `{control_type}` which it doesn't support."
                )

    def set_control_type(self, control_type: ProtocolControlType):
        handshake_received_event = self.controller._handshake_received_event
        resource_manager_details_received = (
            self.controller._resource_manager_details_received
        )

        super().set_control_type(control_type)

        # Copy the events over.
        self.controller._handshake_received_event = handshake_received_event
        self.controller._resource_manager_details_received = (
            resource_manager_details_received
        )

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
