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
from testsuites.test_suite.test_suite import NotApplicableTestException, S2TestCase
from testsuites.util import current_timezone_time
from .base import FRBCCEMTestCase, FRBCCEMTestCase


class FRBCElectricVehicleScenarioTestCase(FRBCCEMTestCase):
    name = "Electric Vehicle Scenario Test Case"

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
                valid_from=datetime.datetime.now(tz=datetime.timezone.utc),
                elements=[
                    FRBCLeakageBehaviourElement(
                        fill_level_range=NumberRange(start_of_range=0, end_of_range=0),
                        leakage_rate=0,
                    )
                ],
            )
        )

    def create_ev_example_frbc_system_description(self):
        self.commodity = Commodity.ELECTRICITY
        self.commodity_quantity = CommodityQuantity.ELECTRIC_POWER_L1

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
        self.actuator = actuator

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
                            start_of_range=0.00065, end_of_range=0.0051
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

    async def generate_tests(self):
        await super().generate_tests()

        await self.add_trigger_method(self.send_frbc_system_description)

        await self.add_trigger_method(self.send_leakage_behaviour)

        if self.actuator is None:
            return

        # Start with not being plugged in.
        actuator_status = FRBCActuatorStatus(
            message_id=uuid.uuid4(),
            actuator_id=self.actuator.id,
            active_operation_mode_id=self.actuator.named_operation_modes["off"],
            operation_mode_factor=0,
            previous_operation_mode_id=None,
            transition_timestamp=None,
        )
        storage_status = FRBCStorageStatus(
            message_id=uuid.uuid4(), present_fill_level=0
        )
        await self.add_trigger_method(
            # "Update Actuator Status (Off)",
            self.send_actuator_status,
            actuator_status,
        )
        await self.add_trigger_method(
            # "Update Storage Status (Empty - No Car Plugged in)",
            self.send_storage_status,
            storage_status,
        )

        # Now start charging
        actuator_status = FRBCActuatorStatus(
            message_id=uuid.uuid4(),
            actuator_id=self.actuator.id,
            active_operation_mode_id=self.actuator.named_operation_modes["charging"],
            operation_mode_factor=0,
            previous_operation_mode_id=self.actuator.named_operation_modes["off"],
            transition_timestamp=None,
        )
        storage_status = FRBCStorageStatus(
            message_id=uuid.uuid4(), present_fill_level=50
        )
        await self.add_trigger_method(
            # "Update Actuator Status (Charging)",
            self.send_actuator_status,
            actuator_status,
        )
        await self.add_trigger_method(
            # "Update Storage Status (50% - Plugged in)",
            self.send_storage_status,
            storage_status,
        )

        power_measurement = PowerMeasurement(
            message_id=uuid.uuid4(),
            measurement_timestamp=current_timezone_time(),
            values=[
                PowerValue(commodity_quantity=self.commodity_quantity, value=10000)
            ],
        )
        await self.add_trigger_method(
            self.send_power_measurement, power_measurement, wait_time=2
        )

        await self.add_trigger_method(
            None,
            self._received_instruction_event,
            wait_time=self.config.instruction_wait_timeout,
        )

        # Wait 10 seconds after receiving instruction
        await self.add_trigger_method(None, wait_time=10)

        await self.add_trigger_method(self.send_power_measurement_using_instructions)

        # await self.add_trigger_method(self.send_revoke_leakage_behaviour)
        # await self.add_trigger_method(self.send_revoke_system_description)

    async def send_power_measurement_using_instructions(self):
        if self.controller is None:
            raise ValueError("No controller provided.")
        instruction = self.controller.instructions.get_active_instruction(
            current_timezone_time()
        )
        power_measurement = PowerMeasurement(
            message_id=uuid.uuid4(),
            measurement_timestamp=current_timezone_time(),
            values=[
                PowerValue(commodity_quantity=self.commodity_quantity, value=10000)
            ],
        )

    async def fold(self):
        await super().generate_tests()
        # Putting the tests here allows me to enforce the ordering.
        await self.add_test_method(
            "9.6.1 Update System Description (initial)",
            self.send_frbc_system_description,
            self.system_description,
        )
        dupe_system_description = self.system_description.model_copy()
        dupe_system_description.message_id = uuid.uuid4()
        await self.add_test_method(
            "9.6.1 Update System Description",
            self.send_frbc_system_description,
            dupe_system_description,
        )
        await self.add_test_method(
            "9.6.3. Update Leakage Behaviour (Initial)",
            self.send_leakage_behaviour,
            self.leakage_behavior,
        )
        dupe_leakage_behaviour = self.leakage_behavior.model_copy()
        dupe_leakage_behaviour.message_id = uuid.uuid4()
        await self.add_test_method(
            "9.6.3. Update Leakage Behaviour",
            self.send_leakage_behaviour,
            dupe_leakage_behaviour,
        )

        # Start with not being plugged in.
        actuator_status = FRBCActuatorStatus(
            message_id=uuid.uuid4(),
            actuator_id=self.actuator.id,
            active_operation_mode_id=self.off_operation_mode.id,
            operation_mode_factor=0,
            previous_operation_mode_id=None,
            transition_timestamp=None,
        )
        storage_status = FRBCStorageStatus(
            message_id=uuid.uuid4(), present_fill_level=0
        )
        await self.add_test_method(
            "Update Actuator Status (Off)",
            self.send_actuator_status,
            actuator_status,
        )
        await self.add_test_method(
            "Update Storage Status (Empty - No Car Plugged in)",
            self.send_storage_status,
            storage_status,
        )

        # Now start charging
        actuator_status = FRBCActuatorStatus(
            message_id=uuid.uuid4(),
            actuator_id=self.actuator.id,
            active_operation_mode_id=self.charging_operation_mode.id,
            operation_mode_factor=0,
            previous_operation_mode_id=self.off_operation_mode.id,
            transition_timestamp=current_timezone_time(),
        )
        storage_status = FRBCStorageStatus(
            message_id=uuid.uuid4(), present_fill_level=50
        )
        await self.add_test_method(
            "Update Actuator Status (Charging)",
            self.send_actuator_status,
            actuator_status,
        )
        await self.add_test_method(
            "Update Storage Status (50% - Plugged in)",
            self.send_storage_status,
            storage_status,
        )

        # Send 2 power measurements with 2 seconds in between
        for i in range(2):
            power_measurement = PowerMeasurement(
                message_id=uuid.uuid4(),
                measurement_timestamp=current_timezone_time(),
                values=[
                    PowerValue(commodity_quantity=self.commodity_quantity, value=10000)
                ],
            )
            await self.add_test_method(
                "Update Power Measurement",
                self.send_power_measurement,
                power_measurement,
                2,
            )

            self.test_logger.info(
                f"Waiting {self.config.instruction_wait_timeout} seconds for an instruction.",
                0,
            )

            await asyncio.sleep(45)
            # await self.add_test_method(
            #     "Wait for instruction",
            #     self.wait_for_instruction,
            #     self.config.instruction_wait_timeout,
            # )

        # Goes at the end since a number of other tests require system description as a precondition.
        await self.add_test_method(
            "9.6.2. Revoke System Description",
            self.send_revoke_system_description,
        )

    async def validate_instruction(self, instruction: FRBCInstruction):
        self.test_logger.info("RECEIVED INSTRUCTION.")
        self.test_logger.info(instruction)

        self.assertIsNotNone(instruction)
        self.assertEqual(type(instruction), FRBCInstruction)
