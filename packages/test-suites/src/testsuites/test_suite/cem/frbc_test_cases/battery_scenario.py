import asyncio
from dataclasses import dataclass
import datetime
import uuid
from connectivity.config import FRBCCEMTestConfig
from connectivity.s2_channel import S2Channel
from s2python.frbc import (
    FRBCSystemDescription,
    FRBCStorageDescription,
    FRBCActuatorDescription,
    FRBCOperationMode,
    FRBCOperationModeElement,
    FRBCLeakageBehaviour,
    FRBCLeakageBehaviourElement,
    FRBCUsageForecast,
    FRBCUsageForecastElement,
    FRBCActuatorStatus,
    FRBCStorageStatus,
    FRBCInstruction,
)
from s2python.common import (
    ControlType as ProtocolControlType,
    EnergyManagementRole,
    PowerForecast,
    PowerMeasurement,
    PowerValue,
    ResourceManagerDetails,
    Handshake,
    NumberRange,
    Commodity,
    PowerRange,
    CommodityQuantity,
    Transition,
    Duration,
    RevokeObject,
    InstructionStatusUpdate,
    InstructionStatus,
)

from testsuites.certificate.certificate import ComplianceReport
from testsuites.controllers.cem import FRBCCEMController
from testsuites.test_logger import TestLogger
from testsuites.test_suite.test_suite import NotApplicableTestException, S2TestCase
from testsuites.util import current_timezone_time
from .base import FRBCCEMTestCase, FRBCCEMTestCase

CHARGE_EFFICIENCY: float = 1.0
DISCHARGE_EFFICIENCY: float = 1.0
CAPACITY_WH: float = 20_000.0
LEAKAGE_W: float = 0.5
INITIAL_FILL_LEVEL: float = 0.5

SIMULATION_DURATION = 60


class FRBCBatteryScenarioTestCase(FRBCCEMTestCase):
    name = "Battery Scenario Test Case"

    def __init__(
        self,
        config: FRBCCEMTestConfig,
        channel: S2Channel,
        controller: FRBCCEMController,
        report: ComplianceReport,
        logger: TestLogger,
    ):
        super().__init__(config, channel, controller, report, logger)

        self.create_ev_example_frbc_system_description()

        self.leakage_behavior = FRBCLeakageBehaviour(
            message_id=uuid.uuid4(),
            valid_from=current_timezone_time(),
            elements=[
                FRBCLeakageBehaviourElement(
                    fill_level_range=NumberRange(start_of_range=0, end_of_range=1),
                    leakage_rate=(LEAKAGE_W / CAPACITY_WH) / 3600,
                )
            ],
        )

        self.controller.add_handler(FRBCInstruction, self.handle_instruction)

        self._simulation_started = asyncio.Event()

    def create_ev_example_frbc_system_description(self):
        self.commodity = Commodity.ELECTRICITY
        self.commodity_quantity = CommodityQuantity.ELECTRIC_POWER_L1
        self.fill_level = INITIAL_FILL_LEVEL

        self.storage_description = FRBCStorageDescription(
            diagnostic_label="Battery",
            fill_level_label="Fraction, 0.0 to 1.0",
            provides_leakage_behaviour=True,
            provides_fill_level_target_profile=False,
            provides_usage_forecast=True,
            fill_level_range=NumberRange(start_of_range=0, end_of_range=1),
        )

        self.operation_modes = {
            "idle": FRBCOperationMode(
                id=uuid.uuid4(),
                elements=[
                    FRBCOperationModeElement(
                        fill_rate=NumberRange(start_of_range=0.0, end_of_range=0.0),
                        fill_level_range=NumberRange(
                            start_of_range=0.0, end_of_range=1.0
                        ),
                        power_ranges=[
                            PowerRange(
                                start_of_range=0.0,
                                end_of_range=0.0,
                                commodity_quantity=self.commodity_quantity,
                            )
                        ],
                    )
                ],
                diagnostic_label="Idle",
                abnormal_condition_only=False,
            ),
            "discharge": FRBCOperationMode(
                id=uuid.uuid4(),
                elements=[
                    FRBCOperationModeElement(
                        fill_rate=NumberRange(
                            start_of_range=0.5
                            * CHARGE_EFFICIENCY
                            * ((5000.0 / CAPACITY_WH) / 3600.0),
                            end_of_range=CHARGE_EFFICIENCY
                            * (5000.0 / CAPACITY_WH / 3600.0),
                        ),
                        fill_level_range=NumberRange(
                            start_of_range=0.0, end_of_range=1.0
                        ),
                        power_ranges=[
                            PowerRange(
                                start_of_range=0.5 * 5_000,
                                end_of_range=5_000,
                                commodity_quantity=self.commodity_quantity,
                            )
                        ],
                    )
                ],
                diagnostic_label="Idle",
                abnormal_condition_only=False,
            ),
            "charge": FRBCOperationMode(
                id=uuid.uuid4(),
                elements=[
                    FRBCOperationModeElement(
                        fill_rate=NumberRange(
                            start_of_range=DISCHARGE_EFFICIENCY
                            * ((5000.0 / CAPACITY_WH) / 3600.0),
                            end_of_range=0.5
                            * DISCHARGE_EFFICIENCY
                            * (5000.0 / CAPACITY_WH / 3600.0),
                        ),
                        fill_level_range=NumberRange(
                            start_of_range=0.0, end_of_range=1.0
                        ),
                        power_ranges=[
                            PowerRange(
                                start_of_range=-5_000,
                                end_of_range=0.5 * -5_000,
                                commodity_quantity=self.commodity_quantity,
                            )
                        ],
                    )
                ],
                diagnostic_label="Idle",
                abnormal_condition_only=False,
            ),
        }

        self.id_to_op_mode: dict[uuid.UUID, str] = {
            self.operation_modes["idle"].id: "idle",
            self.operation_modes["charge"].id: "charge",
            self.operation_modes["discharge"].id: "discharge",
        }

        self.last_updated = current_timezone_time()
        self.active_operation_mode = "idle"
        self.operation_mode_factor = 0.5

        self.actuator = FRBCActuatorDescription(
            id=uuid.uuid4(),
            diagnostic_label="",
            operation_modes=[
                self.operation_modes["idle"],
                self.operation_modes["charge"],
                self.operation_modes["discharge"],
            ],
            transitions=[
                # Idle <--> charging
                Transition(
                    **{
                        "id": uuid.uuid4(),
                        "from": self.operation_modes["idle"].id,
                        "to": self.operation_modes["charge"].id,
                        "start_timers": [],
                        "blocking_timers": [],
                        "transition_duration": None,
                        "abnormal_condition_only": False,
                    }
                ),
                Transition(
                    **{
                        "id": uuid.uuid4(),
                        "from": self.operation_modes["charge"].id,
                        "to": self.operation_modes["idle"].id,
                        "start_timers": [],
                        "blocking_timers": [],
                        "transition_duration": None,
                        "abnormal_condition_only": False,
                    }
                ),
                # Idle <--> discharging
                Transition(
                    **{
                        "id": uuid.uuid4(),
                        "from": self.operation_modes["idle"].id,
                        "to": self.operation_modes["discharge"].id,
                        "start_timers": [],
                        "blocking_timers": [],
                        "transition_duration": None,
                        "abnormal_condition_only": False,
                    }
                ),
                Transition(
                    **{
                        "id": uuid.uuid4(),
                        "from": self.operation_modes["discharge"].id,
                        "to": self.operation_modes["idle"].id,
                        "start_timers": [],
                        "blocking_timers": [],
                        "transition_duration": None,
                        "abnormal_condition_only": False,
                    }
                ),
            ],
            timers=[],
            supported_commodities=[self.commodity],
        )

        self.system_description = FRBCSystemDescription(
            message_id=uuid.uuid4(),
            valid_from=current_timezone_time(),
            actuators=[self.actuator],
            storage=self.storage_description,
        )

    def update(self) -> FRBCStorageStatus:
        delta_time = current_timezone_time() - self.last_updated
        self.last_updated = current_timezone_time()

        fill_rates = (
            self.operation_modes[self.active_operation_mode].elements[0].fill_rate
        )
        fill_rate = (
            fill_rates.start_of_range
            + (fill_rates.end_of_range - fill_rates.start_of_range)
            * self.operation_mode_factor
        )
        self.fill_level += fill_rate * delta_time.seconds

        if self.fill_level > 1:
            self.fill_level = 1
        elif self.fill_level < 0:
            self.fill_level = 0

        return FRBCStorageStatus(
            message_id=uuid.uuid4(), present_fill_level=self.fill_level
        )

    def forecast(self) -> FRBCUsageForecast:
        return FRBCUsageForecast(
            message_id=uuid.uuid4(),
            start_time=current_timezone_time(),
            elements=[
                FRBCUsageForecastElement(
                    duration=Duration(1000 * 3600),
                    usage_rate_expected=0,
                    usage_rate_lower_68PPR=None,
                    usage_rate_lower_95PPR=None,
                    usage_rate_lower_limit=None,
                    usage_rate_upper_68PPR=None,
                    usage_rate_upper_95PPR=None,
                    usage_rate_upper_limit=None,
                )
            ],
        )

    async def handle_instruction(self, instruction: FRBCInstruction):
        await self._simulation_started.wait()
        self.test_logger.info(f"Received instruction: {instruction}")
        if instruction.operation_mode in self.id_to_op_mode:
            self.active_operation_mode = self.id_to_op_mode[instruction.operation_mode]
            self.operation_mode_factor = self.operation_mode_factor
            status_type = InstructionStatus.ACCEPTED
        else:
            status_type = InstructionStatus.REJECTED
        status = InstructionStatusUpdate(
            instruction_id=instruction.message_id,
            status_type=status_type,
            timestamp=current_timezone_time(),
        )
        await self.controller.send_instruction_status_update(self.channel, status)

    async def test_simulate(self):
        self._simulation_started.set()
        self.test_logger.info("Simulation started.")

        for i in range(10):
            await asyncio.sleep(10)

            storage_status = self.update()

            await self.controller.send_storage_status(self.channel, storage_status)

    async def generate_tests(self):
        await super().generate_tests()
        # Putting the tests here allows me to enforce the ordering.
        await self.add_test_method(
            "9.6.1 Update System Description (initial)",
            self.send_frbc_system_description,
            self.system_description,
        )
        await self.add_test_method(
            "9.6.3. Update Leakage Behaviour (Initial)",
            self.send_leakage_behaviour,
            self.leakage_behavior,
        )

        actuator_status = FRBCActuatorStatus(
            message_id=uuid.uuid4(),
            actuator_id=self.actuator.id,
            active_operation_mode_id=self.operation_modes["idle"].id,
            operation_mode_factor=0,
            previous_operation_mode_id=None,
            transition_timestamp=None,
        )
        storage_status = FRBCStorageStatus(
            message_id=uuid.uuid4(), present_fill_level=self.fill_level
        )
        await self.add_test_method(
            "Update Actuator Status (Idle)",
            self.send_actuator_status,
            actuator_status,
        )
        await self.add_test_method(
            "Update Storage Status (Initial)",
            self.send_storage_status,
            storage_status,
        )
        await self.add_test_method(
            "Update Usage Forecast (Initial)",
            self.send_usage_forecast,
            self.forecast(),
        )
        await self.add_test_method("Simulation", self.test_simulate)

        # # Now start discharging
        # actuator_status = FRBCActuatorStatus(
        #     message_id=uuid.uuid4(),
        #     actuator_id=self.actuator.id,
        #     active_operation_mode_id=self.charging_operation_mode.id,
        #     operation_mode_factor=0,
        #     previous_operation_mode_id=self.off_operation_mode.id,
        #     transition_timestamp=current_timezone_time(),
        # )
        # storage_status = FRBCStorageStatus(
        #     message_id=uuid.uuid4(), present_fill_level=50
        # )
        # await self.add_test_method(
        #     "Update Actuator Status (Charging)",
        #     self.test_update_actuator_status,
        #     actuator_status,
        # )
        # await self.add_test_method(
        #     "Update Storage Status (50% - Plugged in)",
        #     self.test_update_storage_status,
        #     storage_status,
        # )

        # # Send 2 power measurements with 2 seconds in between
        # for i in range(2):
        #     power_measurement = PowerMeasurement(
        #         message_id=uuid.uuid4(),
        #         measurement_timestamp=current_timezone_time(),
        #         values=[
        #             PowerValue(commodity_quantity=self.commodity_quantity, value=10000)
        #         ],
        #     )
        #     await self.add_test_method(
        #         "Update Power Measurement",
        #         self.test_update_power_measurement,
        #         power_measurement,
        #         2,
        #     )

        # await self.add_test_method(
        #     "Wait for instruction",
        #     self.wait_for_instruction,
        #     self.config.instruction_wait_timeout,
        # )

        # # Goes at the end since a number of other tests require system description as a precondition.
        # await self.add_test_method(
        #     "9.6.2. Revoke System Description",
        #     self.test_revoke_system_description,
        # )
