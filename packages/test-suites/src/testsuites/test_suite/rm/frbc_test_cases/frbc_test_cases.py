import datetime
import json
import logging
import uuid

from .base import FRBCTestCase
from testsuites.certificate.certificate import (
    TestSuiteResults,
    TestResult,
    ComplianceReport,
    TestResultStatus,
)
from s2python.common import PowerMeasurement, ControlType as ProtocolControlType
from s2python.frbc import (
    FRBCActuatorStatus,
    FRBCStorageDescription,
    FRBCStorageStatus,
    FRBCSystemDescription,
    FRBCUsageForecast,
)
from testsuites.test_suite.test_suite import S2TestCase

logger = logging.getLogger(__name__)


class FRBCSystemDescriptionTestCase(FRBCTestCase):
    name = "Test receive FRBCSystemDescription"

    @S2TestCase.test
    async def test_receive_frbc_system_description(self):
        await self.wait_for_system_description()

        message = await self.check_receive_message_type(FRBCSystemDescription)

        self.test_logger.success("Test Receive FRBC System Description")


class FRBCActuatorStatusTestCase(FRBCTestCase):
    name = "Test Receive FRBC Actuator Status"

    @S2TestCase.test
    async def test_receive_actuator_status(self):
        await self.wait_for_system_description()

        message = await self.check_receive_message_type(FRBCActuatorStatus)

        self.test_logger.success("Test Receive FRBC Actuator Status")


class FRBCStorageStatusTestCase(FRBCTestCase):
    name = "Test receive FRBCStorageStatus"

    @S2TestCase.test("Test Receive FRBC Storage Status")
    async def test_receive_storage_status(self):
        await self.wait_for_system_description()

        message = await self.check_receive_message_type(FRBCStorageStatus)

        self.test_logger.success("Test Receive FRBC Storage Status")


class FRBCUsageForecastTestCase(FRBCTestCase):
    name = "Test receive FRBCUsageForecast"

    @S2TestCase.test
    async def test_receive_usage_forecast(self):
        await self.wait_for_system_description()

        message = await self.check_receive_message_type(FRBCUsageForecast)

        self.test_logger.success("Test Receive FRBC Usage Forecast")
