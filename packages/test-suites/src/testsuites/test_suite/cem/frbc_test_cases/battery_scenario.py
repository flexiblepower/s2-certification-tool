import asyncio
from dataclasses import dataclass
import datetime
from typing import Awaitable, Dict
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
    ReceptionStatus,
    InstructionStatusUpdate,
    InstructionStatus,
)

from testsuites.certificate.certificate import ComplianceReport
from testsuites.controllers.cem import FRBCCEMController
from testsuites.controllers.cem.frbc_controller import ActuatorInformation
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

    actuator_initial_status: Dict[uuid.UUID, FRBCActuatorStatus] = {}

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

        self.controller.set_leakage_behaviour(
            FRBCLeakageBehaviour(
                message_id=uuid.uuid4(),
                valid_from=current_timezone_time(),
                elements=[
                    FRBCLeakageBehaviourElement(
                        fill_level_range=NumberRange(start_of_range=0, end_of_range=1),
                        leakage_rate=(LEAKAGE_W / CAPACITY_WH) / 3600,
                    )
                ],
            )
        )

        self.message_handlers[FRBCInstruction] = self.handle_instruction

        self.fill_level = INITIAL_FILL_LEVEL

        self._simulation_started = asyncio.Event()

    def create_ev_example_frbc_system_description(self):
        self.commodity = Commodity.ELECTRICITY
        self.commodity_quantity = CommodityQuantity.ELECTRIC_POWER_L1

        self.controller.set_storage_description(
            FRBCStorageDescription(
                diagnostic_label="Battery",
                fill_level_label="Fraction, 0.0 to 1.0",
                provides_leakage_behaviour=True,
                provides_fill_level_target_profile=False,
                provides_usage_forecast=True,
                fill_level_range=NumberRange(start_of_range=0, end_of_range=1),
            )
        )

        actuator = ActuatorInformation(
            supported_commodities=[self.commodity],
        )
        self.actuator = actuator

        idle_operation_mode = actuator.add_operation_mode(
            FRBCOperationMode(
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
            name="idle",
        )
        discharge_operation_mode = actuator.add_operation_mode(
            FRBCOperationMode(
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
            name="discharge",
        )

        charge_operation_mode = actuator.add_operation_mode(
            FRBCOperationMode(
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
            name="charge",
        )

        self.last_updated = current_timezone_time()
        self.active_operation_mode = "idle"
        self.operation_mode_factor = 0.5

        # Idle <--> charging
        actuator.add_transition(
            Transition(
                **{
                    "id": uuid.uuid4(),
                    "from": idle_operation_mode.id,
                    "to": charge_operation_mode.id,
                    "start_timers": [],
                    "blocking_timers": [],
                    "transition_duration": None,
                    "abnormal_condition_only": False,
                }
            ),
        )
        actuator.add_transition(
            Transition(
                **{
                    "id": uuid.uuid4(),
                    "from": charge_operation_mode.id,
                    "to": idle_operation_mode.id,
                    "start_timers": [],
                    "blocking_timers": [],
                    "transition_duration": None,
                    "abnormal_condition_only": False,
                }
            ),
        )
        # Idle <--> discharging
        actuator.add_transition(
            Transition(
                **{
                    "id": uuid.uuid4(),
                    "from": idle_operation_mode.id,
                    "to": discharge_operation_mode.id,
                    "start_timers": [],
                    "blocking_timers": [],
                    "transition_duration": None,
                    "abnormal_condition_only": False,
                }
            ),
        )
        actuator.add_transition(
            Transition(
                **{
                    "id": uuid.uuid4(),
                    "from": discharge_operation_mode.id,
                    "to": idle_operation_mode.id,
                    "start_timers": [],
                    "blocking_timers": [],
                    "transition_duration": None,
                    "abnormal_condition_only": False,
                }
            ),
        )

        self.controller.add_actuator(actuator)
        self.controller.generate_system_description()

        self.actuator_initial_status[actuator.id] = FRBCActuatorStatus(
            message_id=uuid.uuid4(),
            actuator_id=actuator.id,
            active_operation_mode_id=idle_operation_mode.id,
            operation_mode_factor=0.5,
            previous_operation_mode_id=None,
            transition_timestamp=None,
        )

    async def update(self):
        delta_time = current_timezone_time() - self.last_updated
        self.last_updated = current_timezone_time()

        # TODO: CHECK INSTRUCTION
        self.test_logger.info("Running Step")
        for actuator in self.controller.actuators.values():
            current_operation_mode = self.controller.get_active_operation_mode(
                actuator.id
            )

            instruction = self.controller.instructions.get_active_instruction(
                actuator_id=actuator.id, timestamp=current_timezone_time()
            )
            if instruction is not None:
                self.test_logger.info(f"Instruction found: {instruction}")
            if (
                instruction is not None
                and instruction.operation_mode != current_operation_mode.id
            ):
                self.test_logger.info(f"Updating instruction status.")
                await self.send_actuator_status(
                    FRBCActuatorStatus(
                        message_id=uuid.uuid4(),
                        active_operation_mode_id=instruction.operation_mode,
                        actuator_id=instruction.actuator_id,
                        operation_mode_factor=instruction.operation_mode_factor,
                        previous_operation_mode_id=current_operation_mode.id,
                        transition_timestamp=current_timezone_time(),
                    )
                )

                current_operation_mode = self.controller.get_active_operation_mode(
                    actuator.id
                )

            # Not sure what to do with the others here... only using 0
            fill_rate_range = current_operation_mode.elements[0].fill_rate
            fill_rate = (
                fill_rate_range.start_of_range
                + (fill_rate_range.end_of_range - fill_rate_range.start_of_range)
                * self.operation_mode_factor
            )
            self.fill_level += fill_rate * delta_time.seconds

            if self.fill_level > 1:
                self.fill_level = 1
            elif self.fill_level < 0:
                self.fill_level = 0

            self.test_logger.info("Updating storage status.")
            await self.controller.update_storage_status(
                self.channel,
                FRBCStorageStatus(
                    message_id=uuid.uuid4(), present_fill_level=self.fill_level
                ),
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

    async def handle_instruction(
        self, instruction: FRBCInstruction, channel: S2Channel, send_okay: Awaitable
    ):
        await self.handle_with_original_handler(instruction, channel, send_okay)

        await self.add_trigger_method(
            self.validate_instruction,
            instruction,
        )

        # await self._simulation_started.wait()
        # self.test_logger.info(f"Received instruction: {instruction}")
        # if instruction.operation_mode in self.id_to_op_mode:
        #     self.active_operation_mode = self.id_to_op_mode[instruction.operation_mode]
        #     self.operation_mode_factor = self.operation_mode_factor
        #     status_type = InstructionStatus.ACCEPTED
        # else:
        #     status_type = InstructionStatus.REJECTED
        # status = InstructionStatusUpdate(
        #     instruction_id=instruction.message_id,
        #     status_type=status_type,
        #     timestamp=current_timezone_time(),
        # )
        # await self.controller.send_instruction_status_update(self.channel, status)

    async def validate_instruction(
        self,
        instruction: FRBCInstruction,
        # status_update: InstructionStatusUpdate,
        # status_update_reception_status: ReceptionStatus,
    ):
        self.assertIsNotNone(instruction)
        self.assertEqual(type(instruction), FRBCInstruction)

        # self.assertIsNotNone(status_update)
        # self.assertEqual(type(status_update), FRBCInstruction)

        # self.assertIsNotNone(status_update_reception_status)
        # self.assertEqual(type(status_update_reception_status), ReceptionStatus)

    async def send_storage_status(self):
        storage_status = FRBCStorageStatus(
            message_id=uuid.uuid4(), present_fill_level=self.fill_level
        )

        return await super().send_storage_status(storage_status)

    async def send_initial_info(self):
        for initial_status in self.actuator_initial_status.values():
            await self.send_actuator_status(initial_status)

        await self.send_storage_status()

        await self.send_power_measurement(
            PowerMeasurement(
                message_id=uuid.uuid4(),
                measurement_timestamp=current_timezone_time(),
                values=[
                    PowerValue(commodity_quantity=self.commodity_quantity, value=0)
                ],
            )
        )

        forecast = self.forecast()
        await self.send_usage_forecast(forecast)

    async def execute_simulation_step(self):
        await self.update()

    async def change_to_discharging(self):
        actuator = list(self.controller.actuators.values())[0]

        discharge_om = actuator.get_named_operation_mode("discharge")
        active_operation_mode_id = self.controller.actuator_status[
            actuator.id
        ].active_operation_mode_id

        if active_operation_mode_id != discharge_om:
            await self.send_actuator_status(
                FRBCActuatorStatus(
                    message_id=uuid.uuid4(),
                    active_operation_mode_id=discharge_om.id,
                    actuator_id=actuator.id,
                    operation_mode_factor=0.5,
                    previous_operation_mode_id=active_operation_mode_id,
                    transition_timestamp=current_timezone_time(),
                )
            )

    async def generate_tests(self):
        await super().generate_tests()

        await self.add_trigger_method(self.send_frbc_system_description)
        await self.add_trigger_method(self.send_leakage_behaviour)

        await self.add_trigger_method(self.send_initial_info)

        NUM_SIMULATION_ITERATIONS = 2
        SIMULATION_STEP_DURATION = 10
        for i in range(NUM_SIMULATION_ITERATIONS):
            await self.add_trigger_method(
                self.execute_simulation_step, wait_time=SIMULATION_STEP_DURATION
            )

        await self.add_trigger_method(
            self.change_to_discharging,
        )

        MAIN_NUM_SIMULATION_ITERATIONS = 20
        for i in range(MAIN_NUM_SIMULATION_ITERATIONS):
            await self.add_trigger_method(
                self.execute_simulation_step, wait_time=SIMULATION_STEP_DURATION
            )
