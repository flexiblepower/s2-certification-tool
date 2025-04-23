import abc
import datetime
from typing import TYPE_CHECKING, Dict, List, Type
import uuid
from message_handlers import Controller, PEBCController
from s2python.common import PowerMeasurement
from s2python.common import ControlType as ProtocolControlType

from s2python.pebc import (
    PEBCAllowedLimitRange,
    PEBCInstruction,
    PEBCPowerEnvelope,
    PEBCPowerEnvelopeElement,
)
from connection import Connection


import logging

logger = logging.getLogger(__name__)


class S2TestCase(abc.ABC):
    control_type: ProtocolControlType = ProtocolControlType.NO_SELECTION

    def __init__(self, connection: Connection, controller: Controller):
        self.connection = connection
        self.controller = controller

    @abc.abstractmethod
    def execute(self):
        pass


class TestSuite:
    test_cases: Dict[ProtocolControlType, List[Type[S2TestCase]]]

    def __init__(self):
        self.test_cases = {}

    def add_test_case(self, test_case: Type[S2TestCase]):
        if self.test_cases.get(test_case.control_type, None) is None:
            self.test_cases[test_case.control_type] = [test_case]
        else:
            self.test_cases[test_case.control_type].append(test_case)

    async def execute(self, connection: Connection, controller: Controller):
        self.controller = controller
        self.connection = connection

        test_cases = self.test_cases[controller.control_type]

        for TestCase in test_cases:
            test_case = TestCase(connection, controller)
            test_case.execute()


class TestSuiteBuilder:
    def __init__(self):
        self.test_suite = TestSuite()

    def with_test_case(self, test_case):
        self.test_suite.add_test_case(test_case)
        return self

    def build(self):
        return self.test_suite


class PEBCTestCase(S2TestCase):
    controller: PEBCController

    async def wait_until_control_type_attrs_set(self):
        power_constraints = self.controller.power_constraints
        if (
            power_constraints is None
            and not self.controller._power_constraints_received.is_set()
        ):
            logger.info(
                "Waiting. %s, %s",
                power_constraints,
                self.controller._power_constraints_received,
            )
            await self.controller._power_constraints_received.wait()
            logger.info("Power Constraints is set.")

    async def test_set_limit_ranges_instruction(self):
        # for limit_ranges in self.power_constraints.allowed_limit_ranges:
        logger.info("Testing set limit range")
        await self.wait_until_control_type_attrs_set()

        power_constraints = self.controller.power_constraints

        if power_constraints is None:
            raise ValueError("Power Constraints not set.")

        limit_range: PEBCAllowedLimitRange = power_constraints.allowed_limit_ranges[1]
        logger.info(power_constraints)
        logger.info("Sending Instruction.")

        # exec_time = datetime.datetime.now()
        exec_time = datetime.datetime.fromisoformat("2025-04-22T09:30:00+00:00")
        # logger.info(exec_time.replace(tzinfo=datetime.timezone.utc))
        logger.info(exec_time)

        instruction = PEBCInstruction(
            message_id=uuid.uuid4(),
            id=power_constraints.id,
            power_constraints_id=power_constraints.id,
            power_envelopes=[
                PEBCPowerEnvelope(
                    id="pe_test",
                    commodity_quantity=limit_range.commodity_quantity,
                    power_envelope_elements=[
                        PEBCPowerEnvelopeElement(
                            lower_limit=-2000.00,
                            upper_limit=0,
                            duration=3600000,
                        )
                    ],
                )
            ],
            # Make it timezone-aware (UTC)
            execution_time=exec_time.replace(tzinfo=datetime.timezone.utc),
            abnormal_condition=False,
        )
        logger.info(instruction)
        await self.connection.send_msg_and_await_reception_status(
            instruction, raise_on_error=True
        )
        logger.info("Instruction sent")

    async def test_receives_interval_power_readings(self):

        if (
            self.controller.config is None
            or self.controller.config.status_update_frequency is None
        ):
            raise ValueError("Status Update Frequency required to test status updates.")

        logger.info("Waiting for power reading.")
        try:
            await self.controller.message_awaiter.wait_for_message(
                PowerMeasurement,
                timeout=float(self.controller.config.status_update_frequency),
            )
            logger.info("Power reading received.")
            await self.controller.message_awaiter.wait_for_message(
                PowerMeasurement,
                timeout=float(
                    self.controller.config.status_update_frequency
                    + self.controller.config.status_update_frequency_buffer
                ),
            )
            logger.info("Power readings test passed.")
        except Exception:
            logger.exception("Did not receive power reading within allowed window.")

    async def execute(self):
        await self.test_receives_interval_power_readings()


def build_test_suite():
    return TestSuiteBuilder().with_test_case(PEBCTestCase).build()
