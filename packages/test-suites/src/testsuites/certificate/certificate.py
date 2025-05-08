import logging
from datetime import datetime
from typing import List, Optional, Type
from enum import Enum

from pydantic import BaseModel, field_serializer
import yaml
from connectivity.config import DeviceDetails

from s2python.message import S2Message

logger = logging.getLogger(__name__)


class ComplianceStatus(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    N_A = "N/A"


class ComplianceParameter(BaseModel):
    name: str
    status: ComplianceStatus

    @field_serializer("status")
    def serializer_status(self, status: ComplianceStatus):
        return status.name


class ComplianceFinding(BaseModel):
    test: str
    status: ComplianceStatus = ComplianceStatus.PASS
    parameters: List[ComplianceParameter] = []

    def add_parameter(
        self,
        name: Optional[str] = None,
        status: Optional[ComplianceStatus] = None,
        param: Optional[ComplianceParameter] = None,
    ):
        if param is None and name is not None and status is not None:
            param = ComplianceParameter(name=name, status=status)
        elif param is None:
            raise ValueError("Either the param must be set or name and status.")

        self.parameters.append(param)

        if param.status == ComplianceStatus.FAIL:
            self.status = ComplianceStatus.FAIL

    @field_serializer("status")
    def serializer_status(self, status: ComplianceStatus):
        return status.name


class ComplianceReport(BaseModel):
    timestamp: datetime = datetime.now()
    findings: List[ComplianceFinding] = []
    device: Optional[DeviceDetails]
    signature: Optional[str] = None

    def add_finding(self, finding: ComplianceFinding):
        self.findings.append(finding)

    def generate_certificate_dict(self) -> dict:
        return self.model_dump()

    def export(self, filename="cert.yaml"):
        if filename is None:
            filename = "cert.yaml"
        with open(filename, "w") as output:
            logger.info("Exporting report to `%s`.", filename)
            cert_data = self.generate_certificate_dict()
            yaml.dump(cert_data, output, default_flow_style=False)
