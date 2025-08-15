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
)

from testsuites.certificate.certificate import ComplianceReport
from testsuites.controllers.cem import FRBCCEMController
from testsuites.controllers.cem.frbc_controller import ActuatorInformation
from testsuites.test_logger import TestLogger
from testsuites.util import current_timezone_time
from .base import FRBCCEMTestCase, FRBCCEMTestCase

CHARGE_EFFICIENCY: float = 1.0
CAPACITY_WH: float = 20_000.0
INITIAL_FILL_LEVEL: float = 0.5


class FRBCElectricVehicleScenarioTestCase(FRBCCEMTestCase):
    name = "Electric Vehicle Scenario Test Case"

    commodity = Commodity.ELECTRICITY
    commodity_quantity = CommodityQuantity.ELECTRIC_POWER_L1

    def __init__(
        self,
        config: FRBCCEMTestConfig,
        channel: S2Channel,
        controller: FRBCCEMController,
        report: ComplianceReport,
        logger: TestLogger,
    ):
        super().__init__(config, channel, controller, report, logger)

    async def create_ev_not_plugged_in_frbc_system_description(self):
        self.controller.reset_system_description()

        self.controller.set_storage_description(
            FRBCStorageDescription(
                diagnostic_label="Battery SoC",
                fill_level_label="EV Battery SoC",
                provides_leakage_behaviour=False,
                provides_fill_level_target_profile=True,
                provides_usage_forecast=False,
                fill_level_range=NumberRange(start_of_range=0, end_of_range=100),
            )
        )

        actuator = ActuatorInformation(
            supported_commodities=[self.commodity],
        )
        self.controller.add_actuator(actuator)

        off_operation_mode = actuator.add_operation_mode(
            FRBCOperationMode(
                id=uuid.uuid4(),
                elements=[
                    FRBCOperationModeElement(
                        fill_level_range=NumberRange(
                            start_of_range=0.0, end_of_range=0.0
                        ),
                        fill_rate=NumberRange(start_of_range=0.0, end_of_range=0.0),
                        power_ranges=[
                            PowerRange(
                                start_of_range=0.0,
                                end_of_range=0.0,
                                commodity_quantity=self.commodity_quantity,
                            )
                        ],
                    )
                ],
                diagnostic_label="Off",
                abnormal_condition_only=False,
            ),
            name="off",
        )
        self.controller.generate_system_description()

        await self.send_frbc_system_description()

        self.controller.set_leakage_behaviour(
            FRBCLeakageBehaviour(
                message_id=uuid.uuid4(),
                valid_from=current_timezone_time(),
                elements=[
                    FRBCLeakageBehaviourElement(
                        fill_level_range=NumberRange(start_of_range=0, end_of_range=0),
                        leakage_rate=0,
                    )
                ],
            )
        )

        await self.send_leakage_behaviour()

        actuator_status = FRBCActuatorStatus(
            message_id=uuid.uuid4(),
            actuator_id=actuator.id,
            active_operation_mode_id=off_operation_mode.id,
            operation_mode_factor=0,
            previous_operation_mode_id=None,
            transition_timestamp=None,
        )
        await self.send_actuator_status(actuator_status)

        storage_status = FRBCStorageStatus(
            message_id=uuid.uuid4(), present_fill_level=0
        )
        self.last_updated = current_timezone_time()
        await self.send_storage_status(storage_status)

    async def create_ev_charging_ev_frbc_system_description(self):
        self.controller.reset_system_description()

        self.controller.set_storage_description(
            FRBCStorageDescription(
                diagnostic_label="Battery SoC",
                fill_level_label="EV Battery SoC",
                provides_leakage_behaviour=False,
                provides_fill_level_target_profile=True,
                provides_usage_forecast=False,
                fill_level_range=NumberRange(start_of_range=0, end_of_range=100),
            )
        )

        actuator = ActuatorInformation(
            supported_commodities=[self.commodity],
        )
        self.controller.add_actuator(actuator)

        off_operation_mode = actuator.add_operation_mode(
            FRBCOperationMode(
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
                                commodity_quantity=self.commodity_quantity,
                            )
                        ],
                    )
                ],
                diagnostic_label="Off",
                abnormal_condition_only=False,
            ),
            name="off",
        )

        charging_operation_mode = actuator.add_operation_mode(
            FRBCOperationMode(
                id=uuid.uuid4(),
                elements=[
                    FRBCOperationModeElement(
                        fill_level_range=NumberRange(
                            start_of_range=0.0, end_of_range=100.0
                        ),
                        fill_rate=NumberRange(
                            start_of_range=0.5
                            * CHARGE_EFFICIENCY
                            * ((5000.0 / CAPACITY_WH) / 3600),
                            end_of_range=CHARGE_EFFICIENCY
                            * (5000.0 / CAPACITY_WH / 3600.0),
                        ),
                        power_ranges=[
                            PowerRange(
                                start_of_range=1400,
                                end_of_range=11000,
                                commodity_quantity=self.commodity_quantity,
                            )
                        ],
                    )
                ],
                diagnostic_label="Charging",
                abnormal_condition_only=False,
            ),
            name="charging",
        )

        actuator.add_transition(
            Transition(
                **{
                    "id": uuid.uuid4(),
                    "from": off_operation_mode.id,
                    "to": charging_operation_mode.id,
                    "start_timers": [],
                    "blocking_timers": [],
                    "transition_duration": Duration(3000),
                    "abnormal_condition_only": False,
                }
            )
        )
        actuator.add_transition(
            Transition(
                **{
                    "id": uuid.uuid4(),
                    "from": charging_operation_mode.id,
                    "to": off_operation_mode.id,
                    "start_timers": [],
                    "blocking_timers": [],
                    "transition_duration": Duration(3000),
                    "abnormal_condition_only": False,
                }
            ),
        )

        self.controller.generate_system_description()
        await self.send_frbc_system_description()

        self.controller.set_leakage_behaviour(
            FRBCLeakageBehaviour(
                message_id=uuid.uuid4(),
                valid_from=current_timezone_time(),
                elements=[
                    FRBCLeakageBehaviourElement(
                        fill_level_range=NumberRange(start_of_range=0, end_of_range=0),
                        leakage_rate=0,
                    )
                ],
            )
        )

        await self.send_leakage_behaviour()

        actuator_status = FRBCActuatorStatus(
            message_id=uuid.uuid4(),
            actuator_id=actuator.id,
            active_operation_mode_id=charging_operation_mode.id,
            operation_mode_factor=0.5,
            previous_operation_mode_id=None,
            transition_timestamp=current_timezone_time(),
        )
        await self.send_actuator_status(actuator_status)

        storage_status = FRBCStorageStatus(
            message_id=uuid.uuid4(), present_fill_level=INITIAL_FILL_LEVEL
        )

        self.last_updated = current_timezone_time()
        await self.send_storage_status(storage_status)

    async def execute_simulation_step(self):
        delta_time = current_timezone_time() - self.last_updated
        self.last_updated = current_timezone_time()

        if self.controller.storage_status is None:
            raise ValueError("Storage status must be set to start the simulation.")

        fill_level = self.controller.storage_status.present_fill_level

        # TODO: CHECK INSTRUCTION
        self.test_logger.info("Running Step")
        for actuator in self.controller.actuators.values():
            if actuator.id in self.controller.actuator_status:
                actuator_status = self.controller.actuator_status[actuator.id]
            else:
                self.test_logger.error("ACTUATOR NOT AVAILABLE")
                continue

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
                actuator_status = FRBCActuatorStatus(
                    message_id=uuid.uuid4(),
                    active_operation_mode_id=instruction.operation_mode,
                    actuator_id=instruction.actuator_id,
                    operation_mode_factor=instruction.operation_mode_factor,
                    previous_operation_mode_id=current_operation_mode.id,
                    transition_timestamp=current_timezone_time(),
                )
                await self.send_actuator_status(actuator_status)

                current_operation_mode = self.controller.get_active_operation_mode(
                    actuator.id
                )

            # Not sure what to do with the others here... only using 0
            fill_rate_range = current_operation_mode.elements[0].fill_rate
            fill_rate = (
                fill_rate_range.start_of_range
                + (fill_rate_range.end_of_range - fill_rate_range.start_of_range)
                * actuator_status.operation_mode_factor
            )
            fill_level += fill_rate * delta_time.seconds
            await self.send_power_measurement(
                PowerMeasurement(
                    message_id=uuid.uuid4(),
                    measurement_timestamp=current_timezone_time(),
                    values=[
                        PowerValue(
                            commodity_quantity=self.commodity_quantity, value=fill_rate
                        )
                    ],
                )
            )

            if fill_level > 1:
                fill_level = 1
            elif fill_level < 0:
                fill_level = 0

            self.test_logger.info("Updating storage status.")
            await self.send_storage_status(
                FRBCStorageStatus(
                    message_id=uuid.uuid4(), present_fill_level=fill_level
                ),
            )

    async def generate_tests(self):
        await super().generate_tests()

        await self.add_trigger_method(
            self.create_ev_not_plugged_in_frbc_system_description, wait_time=10
        )

        NUM_SIMULATION_ITERATIONS = 2
        SIMULATION_STEP_DURATION = 10
        for i in range(NUM_SIMULATION_ITERATIONS):
            await self.add_trigger_method(
                self.execute_simulation_step, wait_time=SIMULATION_STEP_DURATION
            )

        await self.add_trigger_method(
            self.create_ev_charging_ev_frbc_system_description, wait_time=10
        )

        NUM_SIMULATION_ITERATIONS = 2
        SIMULATION_STEP_DURATION = 10
        for i in range(NUM_SIMULATION_ITERATIONS):
            await self.add_trigger_method(
                self.execute_simulation_step, wait_time=SIMULATION_STEP_DURATION
            )

        # power_measurement = PowerMeasurement(
        #     message_id=uuid.uuid4(),
        #     measurement_timestamp=current_timezone_time(),
        #     values=[
        #         PowerValue(commodity_quantity=self.commodity_quantity, value=10000)
        #     ],
        # )
        # await self.add_trigger_method(
        #     self.send_power_measurement, power_measurement, wait_time=2
        # )

        # await self.add_trigger_method(
        #     None,
        #     self._received_instruction_event,
        #     wait_time=self.config.instruction_wait_timeout,
        # )

        # # Wait 10 seconds after receiving instruction
        # await self.add_trigger_method(None, wait_time=10)

    async def validate_instruction(self, instruction: FRBCInstruction):
        self.test_logger.info("RECEIVED INSTRUCTION.")
        self.test_logger.info(instruction)

        self.assertIsNotNone(instruction)
        self.assertEqual(type(instruction), FRBCInstruction)
