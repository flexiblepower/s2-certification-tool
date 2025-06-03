from pydantic import BaseModel
from .base import BaseTestConfig
from typing import Optional
from s2python.common import ControlType as ProtocolControlType, EnergyManagementRole
import logging

logger = logging.getLogger(__name__)


class NoSelectionRMTestConfig(BaseTestConfig):
    pass


class PEBCRMTestConfig(BaseTestConfig):
    status_update_frequency_buffer: int = 5
    sends_energy_constraints: Optional[bool] = None


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
