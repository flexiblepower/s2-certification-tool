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
from testsuites.test_logger import TestLogger
from testsuites.test_suite.test_suite import NotApplicableTestException, S2TestCase
from testsuites.util import current_timezone_time
from .base import FRBCTestCase, FRBCBaseScenarioTestCase


class FRBCElectricVehicleScenarioTestCase(FRBCBaseScenarioTestCase):
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
        self.commodity = Commodity.ELECTRICITY
        self.commodity_quantity = CommodityQuantity.ELECTRIC_POWER_3_PHASE_SYMMETRIC

        self.storage_description = FRBCStorageDescription(
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
                            commodity_quantity=self.commodity_quantity,
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
                            commodity_quantity=self.commodity_quantity,
                        )
                    ],
                )
            ],
            diagnostic_label="Charging",
            abnormal_condition_only=True,
        )

        self.actuator = FRBCActuatorDescription(
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
            supported_commodities=[self.commodity],
        )

        self.system_description = FRBCSystemDescription(
            message_id=uuid.uuid4(),
            valid_from=current_timezone_time(),
            actuators=[self.actuator],
            storage=self.storage_description,
        )

    async def generate_tests(self):
        await super().generate_tests()
        # Putting the tests here allows me to enforce the ordering.
        self.add_test_method(
            "9.6.1 Update System Description (initial)",
            self.test_send_frbc_system_description,
            self.system_description,
        )
        dupe_system_description = self.system_description.model_copy()
        dupe_system_description.message_id = uuid.uuid4()
        self.add_test_method(
            "9.6.1 Update System Description",
            self.test_send_frbc_system_description,
            dupe_system_description,
        )
        self.add_test_method(
            "9.6.3. Update Leakage Behaviour (Initial)",
            self.test_update_leakage_behaviour,
            self.leakage_behavior,
        )
        dupe_leakage_behaviour = self.leakage_behavior.model_copy()
        dupe_leakage_behaviour.message_id = uuid.uuid4()
        self.add_test_method(
            "9.6.3. Update Leakage Behaviour",
            self.test_update_leakage_behaviour,
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
        self.add_test_method(
            "Update Actuator Status (Off)",
            self.test_update_actuator_status,
            actuator_status,
        )
        self.add_test_method(
            "Update Storage Status (Empty - No Car Plugged in)",
            self.test_update_storage_status,
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
        self.add_test_method(
            "Update Actuator Status (Charging)",
            self.test_update_actuator_status,
            actuator_status,
        )
        self.add_test_method(
            "Update Storage Status (50% - Plugged in)",
            self.test_update_storage_status,
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
            self.add_test_method(
                "Update Power Measurement",
                self.test_update_power_measurement,
                power_measurement,
                2,
            )

        self.add_test_method(
            "Wait for instruction",
            self.wait_for_instruction,
            self.config.instruction_wait_timeout,
        )

        # Goes at the end since a number of other tests require system description as a precondition.
        self.add_test_method(
            "9.6.2. Revoke System Description",
            self.test_revoke_system_description,
        )
