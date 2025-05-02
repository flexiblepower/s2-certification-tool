import asyncio
from typing import TYPE_CHECKING, Awaitable, Optional

from s2python.common import (
    ControlType as ProtocolControlType,
    InstructionStatusUpdate,
)
from s2python.pebc import (
    PEBCEnergyConstraint,
    PEBCPowerConstraints,
)
from .controller import BaseController
from connectivity.s2_channel import S2Channel

import logging

logger = logging.getLogger(__name__)


class PEBCController(BaseController):
    control_type = ProtocolControlType.POWER_ENVELOPE_BASED_CONTROL
    power_constraints: Optional[PEBCPowerConstraints] = None

    _power_constraints_received: asyncio.Event

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
        logger.info("Received power constraints.")
        self.power_constraints = message
        self._power_constraints_received.set()

        await send_okay

    async def handle_energy_constraints_message(
        self,
        message: PEBCEnergyConstraint,
        connection: "S2Channel",
        send_okay: Awaitable,
    ):
        await send_okay

    async def handle_instruction_status_update(
        self,
        message: InstructionStatusUpdate,
        connection: "S2Channel",
        send_okay: Awaitable,
    ):
        await send_okay


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
