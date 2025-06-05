from pydantic import BaseModel
from .base import BaseTestConfig
from typing import Optional
from s2python.common import ControlType as ProtocolControlType, EnergyManagementRole
import logging

logger = logging.getLogger(__name__)


class NoSelectionRMTestConfig(BaseTestConfig):
    pass


class PEBCRMTestConfig(BaseTestConfig):
    # Indicates whether of not this device sends energy constraints.
    sends_energy_constraints: Optional[bool] = True

    # The time in seconds to wait for the energy constraints before timing out.
    energy_constraints_wait_timeout: Optional[int] = 0

    # The amount of time to wait after sending an instruction before sending the next instruction
    # (in addition to the instruction processing time specified in RM Details)
    instruction_trigger_wait_time: int = 5

    # Indicates whether to wait for the specified instruction processing time (specified in RM details)
    # after sending an instruction
    wait_instruction_processing_time: bool = True


class FRBCRMTestConfig(BaseTestConfig):
    pass


class ControlTypeRMTestConfig(BaseModel):
    enabled: bool = True
    role: EnergyManagementRole = EnergyManagementRole.RM

    not_controllable: Optional[NoSelectionRMTestConfig]
    pebc: Optional[PEBCRMTestConfig]
    frbc: Optional[FRBCRMTestConfig]

    def get_control_type_config(
        self, control_type: ProtocolControlType
    ) -> NoSelectionRMTestConfig | PEBCRMTestConfig | FRBCRMTestConfig:
        config = {
            ProtocolControlType.NO_SELECTION: self.not_controllable,
            ProtocolControlType.NOT_CONTROLABLE: self.not_controllable,
            ProtocolControlType.POWER_ENVELOPE_BASED_CONTROL: self.pebc,
            ProtocolControlType.FILL_RATE_BASED_CONTROL: self.frbc,
        }[control_type]
        return config
