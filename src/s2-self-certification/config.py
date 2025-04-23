from typing import Optional

import yaml
from pydantic import BaseModel


class NoSelectionConfig(BaseModel):
    pass


class PEBCConfig(BaseModel):
    status_update_frequency: int
    status_update_frequency_buffer: int = 5


class FRBCConfig(BaseModel):
    pass


class ControlTypeDetails(BaseModel):
    no_selection: Optional[NoSelectionConfig]
    pebc: Optional[PEBCConfig]
    frbc: Optional[FRBCConfig]


class DeviceDetails(BaseModel):
    name: str
    manufacturer: str


class Config(BaseModel):
    device_details: DeviceDetails
    control_types: ControlTypeDetails


def load_config(config_path) -> Config:
    with open(config_path) as stream:
        try:
            config = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            print(exc)
    return Config.model_validate(config)
