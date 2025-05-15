from pydantic import BaseModel
from s2python.common import EnergyManagementRole


class BaseTestConfig(BaseModel):
    enabled: bool = True


class ControlTypeTestConfig(BaseModel):
    role: EnergyManagementRole
