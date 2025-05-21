import asyncio
from dataclasses import dataclass
import datetime
import uuid
from connectivity.config import FRBCCEMTestConfig
from connectivity.s2_channel import S2Channel
from s2python.common import ControlType as ProtocolControlType
from s2python.frbc import (
    FRBCSystemDescription,
    FRBCStorageDescription,
    FRBCActuatorDescription,
    FRBCOperationMode,
    FRBCOperationModeElement,
    FRBCLeakageBehaviour,
    FRBCLeakageBehaviourElement,
)
from s2python.common import (
    ControlType as ProtocolControlType,
    EnergyManagementRole,
    PowerForecast,
    PowerMeasurement,
    ResourceManagerDetails,
    Handshake,
    NumberRange,
    Commodity,
    PowerRange,
    CommodityQuantity,
    Transition,
    Duration,
)

from testsuites.certificate.certificate import ComplianceReport
from testsuites.controllers.cem import FRBCCEMController
from testsuites.test_logger import TestLogger
from testsuites.test_suite.test_suite import S2TestCase
from .base import FRBCTestCase


class FRBCSystemDescriptionTestCase(FRBCTestCase):
    name = "Test send FRBC System Description"

    def __init__(
        self,
        config: FRBCCEMTestConfig,
        channel: S2Channel,
        controller: FRBCCEMController,
        report: ComplianceReport,
        logger: TestLogger,
    ):
        super().__init__(config, channel, controller, report, logger)

        self._frbc_system_description_sent_event = asyncio.Event()
        self._frbc_leakage_behavior_sent_event = asyncio.Event()

        self.create_ev_example_frbc_system_description()

        self.leakage_behavior = FRBCLeakageBehaviour(
            message_id=uuid.uuid4(),
            valid_from=datetime.datetime.now(tz=datetime.timezone.utc),
            elements=[
                FRBCLeakageBehaviourElement(
                    fill_level_range=NumberRange(start_of_range=0, end_of_range=0),
                    leakage_rate=0,
                )
            ],
        )

    def create_ev_example_frbc_system_description(self):
        storage_description = FRBCStorageDescription(
            diagnostic_label="Battery SoC",
            fill_level_label="EV Battery SoC",
            provides_leakage_behaviour=False,
            provides_fill_level_target_profile=True,
            provides_usage_forecast=False,
            fill_level_range=NumberRange(start_of_range=0, end_of_range=100),
        )

        self.off_operation_mode = FRBCOperationMode(
            id=uuid.uuid4(),
            elements=[
                FRBCOperationModeElement(
                    fill_level_range=NumberRange(
                        start_of_range=0.0, end_of_range=100.0
                    ),
                    fill_rate=NumberRange(start_of_range=0.0, end_of_range=0.0),
                    power_ranges=[
                        PowerRange(
                            start_of_range=0.0,
                            end_of_range=0.0,
                            commodity_quantity=CommodityQuantity.ELECTRIC_POWER_3_PHASE_SYMMETRIC,
                        )
                    ],
                )
            ],
            diagnostic_label="Off",
            abnormal_condition_only=True,
        )
        self.charging_operation_mode = FRBCOperationMode(
            id=uuid.uuid4(),
            elements=[
                FRBCOperationModeElement(
                    fill_level_range=NumberRange(
                        start_of_range=0.0, end_of_range=100.0
                    ),
                    fill_rate=NumberRange(start_of_range=0.00065, end_of_range=0.0051),
                    power_ranges=[
                        PowerRange(
                            start_of_range=1400,
                            end_of_range=11000,
                            commodity_quantity=CommodityQuantity.ELECTRIC_POWER_3_PHASE_SYMMETRIC,
                        )
                    ],
                )
            ],
            diagnostic_label="Charging",
            abnormal_condition_only=True,
        )

        actuators = [
            FRBCActuatorDescription(
                id=uuid.uuid4(),
                diagnostic_label="",
                operation_modes=[self.off_operation_mode, self.charging_operation_mode],
                transitions=[
                    Transition(
                        **{
                            "id": uuid.uuid4(),
                            "from": self.off_operation_mode.id,
                            "to": self.charging_operation_mode.id,
                            "start_timers": [],
                            "blocking_timers": [],
                            "transition_duration": Duration(3000),
                            "abnormal_condition_only": True,
                        }
                    ),
                    Transition(
                        **{
                            "id": uuid.uuid4(),
                            "from": self.charging_operation_mode.id,
                            "to": self.off_operation_mode.id,
                            "start_timers": [],
                            "blocking_timers": [],
                            "transition_duration": Duration(3000),
                            "abnormal_condition_only": True,
                        }
                    ),
                ],
                timers=[],
                supported_commodities=[Commodity.ELECTRICITY],
            )
        ]

        self.system_description = FRBCSystemDescription(
            message_id=uuid.uuid4(),
            valid_from=datetime.datetime.now(tz=datetime.timezone.utc),
            actuators=actuators,
            storage=storage_description,
        )

    async def setup(self):
        await super().setup()

        # Only send the FRBC System Description once.
        if not self._frbc_system_description_sent_event.is_set():
            await self.controller.send_frbc_system_description(
                self.channel, self.system_description
            )
            self._frbc_system_description_sent_event.set()

        # Only send the FRBC Leakage Behavior once.
        if not self._frbc_leakage_behavior_sent_event.is_set():
            await self.controller.send_frbc_leakage_behavior(
                self.channel, self.leakage_behavior
            )
            self._frbc_leakage_behavior_sent_event.set()

    @S2TestCase.test("Sent FRBC System Description")
    async def sent_frbc_system_description(self):
        self.assertTrue(self._frbc_system_description_sent_event.is_set())

    @S2TestCase.test("Test Send Leakage Behavior")
    async def sent_frbc_leakage_behaviour(self):
        self.assertTrue(self._frbc_leakage_behavior_sent_event.is_set())

    @S2TestCase.test("Test Send Storage Status")
    async def send_storage_status(self):
        pass

    # @S2TestCase.test("Test Send FRBC System Description Again")
    # async def send_frbc_system_description_again(self):
    #     second_description = self.system_description.copy()
    #     second_description.message_id = uuid.uuid4()
    #     await self.controller.send_frbc_system_description(
    #         self.channel, second_description
    #     )
