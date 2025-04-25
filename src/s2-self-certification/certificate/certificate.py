from email import message
import logging
from datetime import datetime
import json
from typing import List, Optional, Type
from enum import Enum

from black.output import out
from pydantic import BaseModel, field_serializer
import yaml

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
    message_type: Type[S2Message]
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

    @field_serializer("message_type")
    def serializer_message_type(self, message_type: Type[S2Message]):
        return message_type.__name__


class ComplianceReport(BaseModel):
    timestamp: datetime = datetime.now()
    findings: List[ComplianceFinding] = []

    def add_finding(self, finding: ComplianceFinding):
        self.findings.append(finding)

    def generate_certificate_dict(self) -> dict:
        return self.model_dump()

    def export(self, filename="cert.yaml"):
        with open(filename, "w") as output:
            logger.info("Exporting report to `%s`.", filename)
            cert_data = self.generate_certificate_dict()
            yaml.dump(cert_data, output, default_flow_style=False)
