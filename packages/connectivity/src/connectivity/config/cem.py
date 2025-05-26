from pydantic import BaseModel
from .base import BaseTestConfig
from typing import Dict, Optional
from s2python.common import ControlType as ProtocolControlType, EnergyManagementRole


class NoSelectionCEMTestConfig(BaseTestConfig):
    pass


class PEBCCEMTestConfig(BaseTestConfig):
    pass


class FRBCCEMTestConfig(BaseTestConfig):
    pass


class ControlTypeCEMTestConfig(BaseModel):
    enabled: bool = True
    role: EnergyManagementRole = EnergyManagementRole.CEM

    not_controllable: Optional[BaseTestConfig] = None
    pebc: Optional[PEBCCEMTestConfig] = None
    frbc: Optional[FRBCCEMTestConfig] = None

    def get_controller_configs_dics(
        self,
    ) -> Dict[ProtocolControlType, BaseTestConfig | None]:
        return {
            ProtocolControlType.NO_SELECTION: self.not_controllable,
            ProtocolControlType.NOT_CONTROLABLE: self.not_controllable,
            ProtocolControlType.POWER_ENVELOPE_BASED_CONTROL: self.pebc,
            ProtocolControlType.FILL_RATE_BASED_CONTROL: self.frbc,
        }

    def get_control_type_config(self, control_type: ProtocolControlType):
        return self.get_controller_configs_dics()[control_type]

    def get_enabled_control_types(self):
        control_types = []
        for control_type, config in self.get_controller_configs_dics().items():
            if config is not None and config.enabled:
                control_types.append(control_type)
        return control_types
