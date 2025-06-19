import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Type
from enum import Enum

from pydantic import (
    BaseModel,
    field_serializer,
    field_validator,
    model_validator,
    validator,
)
import yaml
from connectivity.config import DeviceDetails

from s2python.message import S2Message
from s2python.common import ControlType as ProtocolControlType
import xml.etree.ElementTree as ET
from connectivity.config import ReportConfig

logger = logging.getLogger(__name__)


class TestResultStatus(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SOFT_FAIL = "SOFT_FAIL"
    N_A = "N/A"


class TestResult(BaseModel):
    name: str
    status: TestResultStatus
    message: Optional[str] = None
    duration: Optional[float] = None
    parameters: Optional[Dict] = None

    @field_serializer("status")
    def serializer_status(self, status: TestResultStatus):
        return status.name

    @field_validator("status", mode="before")
    @classmethod
    def deserialize_status(cls, status):
        if isinstance(status, TestResultStatus):
            return status
        return TestResultStatus[status]


class TestSuiteResults(BaseModel):
    name: str
    control_type: Optional[ProtocolControlType] = None
    duration: Optional[float] = None
    status: TestResultStatus = TestResultStatus.PASS
    tests: Dict[str, TestResult] = {}

    def add_test_result(self, result: TestResult):

        self.tests[result.name] = result
        # self.tests.append(result)

        if result.status in [TestResultStatus.N_A, TestResultStatus.PASS]:
            """No change to the test status."""
        elif result.status == TestResultStatus.FAIL:
            self.status = TestResultStatus.FAIL
        elif result.status == TestResultStatus.SOFT_FAIL and self.status not in [
            TestResultStatus.SOFT_FAIL,
            TestResultStatus.FAIL,
        ]:
            # Soft fail doesn't cause whole failure
            self.status = TestResultStatus.PASS

    @field_serializer("status")
    def serializer_status(self, status: TestResultStatus):
        return status.name

    @field_validator("status", mode="before")
    @classmethod
    def deserialize_status(cls, status):
        if isinstance(status, TestResultStatus):
            return status
        return TestResultStatus[status]

    @field_serializer("control_type")
    def serializer_control_type(self, control_type: Optional[ProtocolControlType]):
        if control_type is None:
            return None
        return control_type.name

    @field_validator("control_type", mode="before")
    @classmethod
    def deserialize_control_type(
        cls, control_type: Optional[str | ProtocolControlType]
    ):
        if control_type is None:
            return None

        if isinstance(control_type, ProtocolControlType):
            return control_type
        return ProtocolControlType[control_type]

    @property
    def count_passed(self, include_soft_fail=False):
        count = 0
        for test in self.tests.values():
            if test.status == TestResultStatus.PASS:
                count += 1
            elif include_soft_fail and test.status == TestResultStatus.SOFT_FAIL:
                count += 1
        return count

    @property
    def count_failed(self, include_soft_fail=True):
        count = 0
        for test in self.tests.values():
            if test.status == TestResultStatus.FAIL:
                count += 1
            elif include_soft_fail and test.status == TestResultStatus.SOFT_FAIL:
                count += 1
        return count

    @property
    def count_skipped(self):
        count = 0
        for test in self.tests.values():
            if test.status == TestResultStatus.N_A:
                count += 1
        return count

    def model_dump(self, *args, include_test_parameters=False, **kwargs):
        dump = super().model_dump(*args, exclude={"tests"}, **kwargs)

        ex = {}
        if not include_test_parameters:
            ex = {"parameters"}

        dump["tests"] = [
            suite.model_dump(exclude=ex, exclude_none=True)
            for suite in self.tests.values()
        ]
        # dump["tests"] = [
        #     suite.model_dump(exclude=ex, exclude_none=True) for suite in self.tests
        # ]

        return dump

    # @model_validator(mode='before')
    # @classmethod
    # def validate_tests(cls, data : Any):

    #     if "test" not in data:
    #         return data

    #     if isinstance(data["tests"], dict):
    #         return data

    #     tests = data["tests"]
    #     data["tests"] = {}

    #     for test in tests:
    #         data["tests"][test["name"]] = test

    #     return data
    @model_validator(mode="before")
    @classmethod
    def _coerce_tests_list(cls, data: Any) -> Any:
        # only rewrite if the raw input has a list under "tests"
        if "tests" not in data or isinstance(data["tests"], dict):
            return data

        # build a dict[name -> test_payload]
        tests_list = data["tests"]
        data["tests"] = {t["name"]: t for t in tests_list}
        return data


class Signature(BaseModel):
    server_signature: Optional[str] = None
    server_signature_timestamp: Optional[datetime] = None

    client_id: Optional[str] = None
    client_signature: Optional[str] = None
    client_signature_timestamp: Optional[datetime] = None


class ComplianceReport(BaseModel):
    timestamp: datetime = datetime.now()
    test_suites: List[TestSuiteResults] = []
    device: Optional[DeviceDetails]
    signature: Signature = Signature()

    def add_test_suite_result(self, result: TestSuiteResults):
        self.test_suites.append(result)

    def generate_certificate_dict(self, include_test_parameters=False) -> dict:

        dump = self.model_dump(exclude_none=True, exclude={"test_suites"})

        dump["test_suites"] = [
            suite.model_dump(
                include_test_parameters=include_test_parameters, exclude_none=True
            )
            for suite in self.test_suites
        ]

        return dump

    def export(self, config: ReportConfig):
        if config.yaml is not None:
            self.export_to_yaml(config.yaml, config.include_test_parameters)
        if config.xml is not None:
            self.export_to_junit_xml(config.xml, config.xml_soft_fail_is_fail)

    def export_to_yaml(self, filename, include_test_parameters):
        logger.info(f"Writing YAML report to `{filename}`")
        with open(filename, "w") as output:
            cert_data = self.generate_certificate_dict(
                include_test_parameters=include_test_parameters
            )
            yaml.dump(cert_data, output, default_flow_style=False)

    @staticmethod
    def _format_duration_xml(seconds: Optional[float]) -> str:
        """Formats duration for XML, handles None."""
        if seconds is None:
            return "0.000"
        return f"{seconds:.3f}"

    def export_to_junit_xml(self, filename, soft_fail_is_fail=True) -> Optional[str]:
        """
        Exports the compliance report to JUnit XML format.
        If filename is provided, writes to the file.
        Otherwise, returns the XML string.
        """

        overall_total_tests = 0
        overall_total_failures = 0
        overall_total_skipped = 0
        overall_total_errors = 0
        overall_total_duration = 0.0

        report_name = "Compliance Test Run"
        if self.device and self.device.name:
            report_name = f"Compliance Test for {self.device.name}"

        report_timestamp_str = self.timestamp.isoformat()

        root_testsuites_element = ET.Element("testsuites")

        for suite in self.test_suites:
            suite_name = f"{suite.name} ({str(suite.control_type)})"
            suite_duration = suite.duration if suite.duration else 0
            suite_num_tests = len(suite.tests)
            suite_num_failures = suite.count_failed
            suite_num_skipped = suite.count_skipped
            suite_num_errors = 0

            testsuite_element = ET.SubElement(
                root_testsuites_element,
                "testsuite",
                name=suite_name,
                timestamp=report_timestamp_str,  # Use main report timestamp for all suites
                tests=str(suite_num_tests),
                failures=str(suite_num_failures),
                errors=str(suite_num_errors),
                skipped=str(suite_num_skipped),
                time=self._format_duration_xml(suite_duration),
            )

            for test_case in suite.tests.values():
                testcase_element = ET.SubElement(
                    testsuite_element,
                    "testcase",
                    name=test_case.name,
                    classname=suite_name,
                    time=self._format_duration_xml(test_case.duration),
                )

                if test_case.status == TestResultStatus.FAIL:
                    failure_element = ET.SubElement(
                        testcase_element,
                        "failure",
                        message=test_case.message or "Test failed",
                        type="Failure",
                    )
                    if test_case.parameters:
                        failure_element.text = f"Parameters: {test_case.parameters}"
                elif (
                    test_case.status == TestResultStatus.SOFT_FAIL and soft_fail_is_fail
                ):
                    failure_element = ET.SubElement(
                        testcase_element,
                        "failure",
                        message=f"[SOFT FAIL] {test_case.message or 'Test soft failed'}",
                        type="SoftFailure",
                    )
                    if test_case.parameters:
                        failure_element.text = f"Parameters: {test_case.parameters}"
                elif test_case.status == TestResultStatus.N_A:
                    ET.SubElement(testcase_element, "skipped")

            overall_total_tests += suite_num_tests
            overall_total_failures += suite_num_failures
            overall_total_skipped += suite_num_skipped
            overall_total_errors += suite_num_errors
            overall_total_duration += suite_duration

        root_testsuites_element.set("name", report_name)
        root_testsuites_element.set("tests", str(overall_total_tests))
        root_testsuites_element.set("failures", str(overall_total_failures))
        root_testsuites_element.set("errors", str(overall_total_errors))
        root_testsuites_element.set("skipped", str(overall_total_skipped))
        root_testsuites_element.set(
            "time", self._format_duration_xml(overall_total_duration)
        )

        # Create XML tree and get string representation
        xml_tree = ET.ElementTree(root_testsuites_element)
        try:
            ET.indent(xml_tree, space="  ")  # Python 3.9+ for pretty printing
        except AttributeError:
            pass  # No pretty printing for older Python

        if filename:
            xml_tree.write(filename, encoding="utf-8", xml_declaration=True)
            logger.info(f"Writing JUnit XML report to `{filename}`")
            return None
        else:
            # To return as string
            from io import BytesIO

            xml_bytes_io = BytesIO()
            xml_tree.write(xml_bytes_io, encoding="utf-8", xml_declaration=True)
            return xml_bytes_io.getvalue().decode("utf-8")
