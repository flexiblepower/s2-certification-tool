import asyncio
import datetime
import logging
from typing import Optional
import uuid
from s2python.common import ControlType as ProtocolControlType
from s2python.frbc import (
    FRBCSystemDescription,
    FRBCStorageDescription,
    FRBCActuatorDescription,
    FRBCOperationMode,
    FRBCOperationModeElement,
)
from .base import BaseCEMController
from connectivity.s2_channel import S2Channel

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


class FRBCCEMCOntroller(BaseCEMController):
    control_type = ProtocolControlType.FILL_RATE_BASED_CONTROL
    system_description: FRBCSystemDescription

    def __init__(self, resource_manager_details: ResourceManagerDetails):
        super().__init__(resource_manager_details)

        storage_description = FRBCStorageDescription(
            diagnostic_label="Battery SoC",
            fill_level_label="EV Battery SoC",
            provides_leakage_behaviour=False,
            provides_fill_level_target_profile=True,
            provides_usage_forecast=False,
            fill_level_range=NumberRange(start_of_range=0, end_of_range=100),
        )

        # actuators = FRBCActuatorDescription(
        #     id="act1",
        #     diagnostic_label="EV Charger",
        #     supported_commodities=Commodity.ELECTRICITY,
        #     operation_modes=[
        #         FRBC
        #     ]
        # )

        off_op_mode_id = uuid.uuid4()
        charging_op_mode_id = uuid.uuid4()

        actuators = [
            FRBCActuatorDescription(
                id=uuid.uuid4(),
                diagnostic_label="",
                operation_modes=[
                    FRBCOperationMode(
                        id=off_op_mode_id,
                        elements=[
                            FRBCOperationModeElement(
                                fill_level_range=NumberRange(
                                    start_of_range=0.0, end_of_range=100.0
                                ),
                                fill_rate=NumberRange(
                                    start_of_range=0.0, end_of_range=0.0
                                ),
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
                    ),
                    FRBCOperationMode(
                        id=charging_op_mode_id,
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
                                        commodity_quantity=CommodityQuantity.ELECTRIC_POWER_3_PHASE_SYMMETRIC,
                                    )
                                ],
                            )
                        ],
                        diagnostic_label="Charging",
                        abnormal_condition_only=True,
                    ),
                ],
                transitions=[
                    Transition(
                        **{
                            "id": uuid.uuid4(),
                            "from": off_op_mode_id,
                            "to": charging_op_mode_id,
                            "start_timers": [],
                            "blocking_timers": [],
                            "transition_duration": Duration(3000),
                            "abnormal_condition_only": True,
                        }
                    ),
                    Transition(
                        **{
                            "id": uuid.uuid4(),
                            "from": charging_op_mode_id,
                            "to": off_op_mode_id,
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

    async def send_frbc_system_description(self, channel: Optional[S2Channel]):
        if channel is None:
            raise ValueError("Channel not set.")

        await channel.send_msg_and_await_reception_status(self.system_description)
