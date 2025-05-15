from pydantic import BaseModel
from .base import BaseTestConfig
from typing import Optional
from s2python.common import ControlType as ProtocolControlType, EnergyManagementRole


class NoSelectionRMTestConfig(BaseTestConfig):
    pass


class PEBCRMTestConfig(BaseTestConfig):
    status_update_frequency: int
    status_update_frequency_buffer: int = 5


class FRBCRMTestConfig(BaseTestConfig):
    pass


class ControlTypeRMTestConfig(BaseModel):
    enabled: bool = True
    role: EnergyManagementRole = EnergyManagementRole.RM

    no_selection: Optional[NoSelectionRMTestConfig]
    pebc: Optional[PEBCRMTestConfig]
    frbc: Optional[FRBCRMTestConfig]

    def get_control_type_config(
        self, control_type: ProtocolControlType
    ) -> NoSelectionRMTestConfig | PEBCRMTestConfig | FRBCRMTestConfig:
        return {
            ProtocolControlType.NO_SELECTION: self.no_selection,
            ProtocolControlType.POWER_ENVELOPE_BASED_CONTROL: self.pebc,
            ProtocolControlType.FILL_RATE_BASED_CONTROL: self.frbc,
        }[control_type]
