import asyncio
import uuid
from typing import Awaitable


from s2python.version import S2_VERSION
from s2python.common import (
    ControlType as ProtocolControlType,
    EnergyManagementRole,
    PowerForecast,
    PowerMeasurement,
    ResourceManagerDetails,
    Handshake,
)
from connectivity.s2_channel import S2Channel

from ..controller import Controller

import logging

logger = logging.getLogger(__name__)


class BaseCEMController(Controller):
    role = EnergyManagementRole.RM
    control_type = ProtocolControlType.NO_SELECTION

    def __init__(self, resource_manager_details: ResourceManagerDetails):
        super().__init__()

        self.resource_manager_details = resource_manager_details

        self.add_handler(Handshake, self.handle_handshake)


    async def send_resource_manager_details(self, channel: S2Channel):
        if self.resource_manager_details is None:
            raise ValueError("Resource Manager Details must be set.")
        await channel.send_msg_and_await_reception_status(self.resource_manager_details)
