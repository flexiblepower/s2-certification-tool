import logging
from typing import Dict, Optional, Literal

import yaml
from pydantic import BaseModel, model_validator
from s2python.common import ControlType as ProtocolControlType, EnergyManagementRole
from .base import BaseTestConfig
from .cem import ControlTypeCEMTestConfig
from .rm import ControlTypeRMTestConfig

logger = logging.getLogger(__name__)


class DeviceDetails(BaseModel):
    name: str
    manufacturer: str


class ConnectionConfig(BaseModel):
    mode: Literal["server", "client"] = "client"
    host: Optional[str] = "0.0.0.0"
    port: Optional[int] = 8000
    uri: Optional[str] = None

    @model_validator(mode="after")
    def check_mode_fields(cls, values):
        if values.mode == "client":
            if not values.uri:
                raise ValueError("For client mode, 'uri' must be provided.")
        elif values.mode == "server":
            if not values.host or values.port is None:
                raise ValueError("For server mode, 'host' and 'port' must be provided.")
        return values


class CertificationConfig(BaseModel):
    uri: str


class ReportConfig(BaseModel):
    yaml: Optional[str] = None
    xml: Optional[str] = None
    xml_soft_fail_is_fail: bool = True
    include_test_parameters: bool = True


class RoleTestConfig(BaseModel):
    rm: ControlTypeRMTestConfig
    cem: ControlTypeCEMTestConfig

    def get_test_config(self, role: EnergyManagementRole):
        match role:
            case EnergyManagementRole.RM:
                return self.rm
            case EnergyManagementRole.CEM:
                return self.cem

    def get_control_type_config(
        self, role: EnergyManagementRole, control_type: ProtocolControlType
    ) -> BaseTestConfig | None:
        match role:
            case EnergyManagementRole.RM:
                return self.rm.get_control_type_config(control_type)
            case EnergyManagementRole.CEM:
                return self.cem.get_control_type_config(control_type)


class Config(BaseModel):
    mode: Literal["testing", "certification"]
    connection: ConnectionConfig
    certification: Optional[CertificationConfig] = None
    device_details: Optional[DeviceDetails] = None
    roles: RoleTestConfig
    report: Optional[ReportConfig] = ReportConfig()


def load_config(config_path) -> Config:
    with open(config_path) as stream:
        try:
            config = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            logger.error("Failed to load yaml config file.")
            raise
    return Config.model_validate(config)
