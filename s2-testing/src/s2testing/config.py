import logging
from typing import Optional, Literal

import yaml
from pydantic import BaseModel
from s2python.common import ControlType as ProtocolControlType

logger = logging.getLogger(__name__)


class BaseTestConfig(BaseModel):
    enabled: bool = True
    pass


class NoSelectionTestConfig(BaseTestConfig):
    pass


class PEBCTestConfig(BaseTestConfig):
    status_update_frequency: int
    status_update_frequency_buffer: int = 5


class FRBCTestConfig(BaseTestConfig):
    pass


class ControlTypeTestConfig(BaseModel):
    no_selection: Optional[NoSelectionTestConfig]
    pebc: Optional[PEBCTestConfig]
    frbc: Optional[FRBCTestConfig]

    def get_control_type_config(
        self, control_type: ProtocolControlType
    ) -> NoSelectionTestConfig | PEBCTestConfig | FRBCTestConfig:
        return {
            ProtocolControlType.NO_SELECTION: self.no_selection,
            ProtocolControlType.POWER_ENVELOPE_BASED_CONTROL: self.pebc,
            ProtocolControlType.FILL_RATE_BASED_CONTROL: self.frbc,
        }[control_type]


class DeviceDetails(BaseModel):
    name: str
    manufacturer: str


class Config(BaseModel):
    mode: Literal["testing", "certification"]
    device_details: DeviceDetails
    control_types: ControlTypeTestConfig


def load_config(config_path) -> Config:
    with open(config_path) as stream:
        try:
            config = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            logger.error("Failed to load yaml config file.")
            raise
    return Config.model_validate(config)
