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
DISCHARGE_EFFICIENCY: float = 1.0
CAPACITY_WH: float = 20_000.0
LEAKAGE_W: float = 0.5
INITIAL_FILL_LEVEL: float = 0.5


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

    async def add_initial_triggers(self):
        """
        The trigger definitions to send the initial data to the CEM.
        Start with car unplugged and storage status 0%
        """

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

    async def add_car_plugged_in_triggers(self):
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

    async def generate_tests(self):
        await super().generate_tests()

        await self.add_initial_triggers()

        # Just wait a little for any unexpected behaviour to happen
        await self.add_trigger_method(None, wait_time=10)

        await self.add_car_plugged_in_triggers()

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

        # await self.add_trigger_method(self.send_power_measurement_using_instructions)

        # await self.add_trigger_method(self.send_revoke_leakage_behaviour)
        # await self.add_trigger_method(self.send_revoke_system_description)

    # async def send_power_measurement_using_instructions(self):
    #     if self.controller is None:
    #         raise ValueError("No controller provided.")

    #     instruction = self.controller.instructions.get_active_instruction(
    #         current_timezone_time()
    #     )
    #     power_measurement = PowerMeasurement(
    #         message_id=uuid.uuid4(),
    #         measurement_timestamp=current_timezone_time(),
    #         values=[
    #             PowerValue(commodity_quantity=self.commodity_quantity, value=10000)
    #         ],
    #     )

    async def validate_instruction(self, instruction: FRBCInstruction):
        self.test_logger.info("RECEIVED INSTRUCTION.")
        self.test_logger.info(instruction)

        self.assertIsNotNone(instruction)
        self.assertEqual(type(instruction), FRBCInstruction)
