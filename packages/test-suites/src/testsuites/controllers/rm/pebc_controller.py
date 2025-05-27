import asyncio
import datetime
from typing import Awaitable, List, Optional
import uuid

from s2python.common import ControlType as ProtocolControlType, InstructionStatusUpdate
from s2python.pebc import (
    PEBCEnergyConstraint,
    PEBCPowerConstraints,
    PEBCInstruction,
    PEBCPowerEnvelope,
)
from .base import BaseRMController
from connectivity.s2_channel import S2Channel

import logging

logger = logging.getLogger(__name__)


class PEBCRMController(BaseRMController):
    control_type = ProtocolControlType.POWER_ENVELOPE_BASED_CONTROL
    power_constraints: Optional[PEBCPowerConstraints] = None
    energy_constraints: Optional[PEBCEnergyConstraint] = None

    _power_constraints_received: asyncio.Event
    _energy_constraints_received: asyncio.Event

    def __init__(self):
        super().__init__()

        self.power_constraints = None
        self._power_constraints_received = asyncio.Event()

        self.add_handler(PEBCPowerConstraints, self.handle_power_constraints_message)
        self.add_handler(PEBCEnergyConstraint, self.handle_energy_constraints_message)
        self.add_handler(InstructionStatusUpdate, self.handle_instruction_status_update)

    async def handle_power_constraints_message(
        self,
        message: PEBCPowerConstraints,
        channel: "S2Channel",
        send_okay: Awaitable,
    ):
        self.power_constraints = message
        self._power_constraints_received.set()

        await send_okay

    async def handle_energy_constraints_message(
        self,
        message: PEBCEnergyConstraint,
        connection: "S2Channel",
        send_okay: Awaitable,
    ):
        self.energy_constraints = message
        self._energy_constraints_received.set()
        await send_okay

    async def handle_instruction_status_update(
        self,
        message: InstructionStatusUpdate,
        connection: "S2Channel",
        send_okay: Awaitable,
    ):
        await send_okay

    async def send_power_envelope_instruction(
        self,
        channel: "S2Channel",
        power_envelopes: List[PEBCPowerEnvelope],
        execution_time: datetime.datetime = datetime.datetime.now(
            datetime.timezone.utc
        ),
    ) -> PEBCInstruction:
        if self.power_constraints is None:
            raise ValueError("Power Constraints not set.")

        instruction = PEBCInstruction(
            message_id=uuid.uuid4(),
            id=uuid.uuid4(),  # ? TODO: Should this be a new UUID?
            power_constraints_id=self.power_constraints.id,
            power_envelopes=power_envelopes,
            # Make it timezone-aware (UTC)
            execution_time=execution_time,
            abnormal_condition=False,
        )

        await channel.send_msg_and_await_reception_status(instruction, 5)

        return instruction


# class PEBCComplianceReportController(PEBCController):

#     def __init__(self, compliance_report: ComplianceReport):
#         super().__init__()

#         self.compliance_report: ComplianceReport = compliance_report

#     async def handle_power_constraints_message(
#         self,
#         message: PEBCPowerConstraints,
#         connection: "Connection",
#         send_okay: Awaitable,
#     ):
#         logger.info("TEST")
#         await super().handle_power_constraints_message(message, connection, send_okay)

#         finding = ComplianceFinding(PEBCPowerConstraints)
#         finding.add_parameter(
#             ComplianceParameter("PEBCPowerConstraints Provided.", ComplianceStatus.PASS)
#         )

#         self.compliance_report.add_finding(finding)

#         logger.info()
