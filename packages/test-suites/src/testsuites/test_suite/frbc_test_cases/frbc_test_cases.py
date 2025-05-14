import datetime
import json
import logging
import uuid

from .base import FRBCTestCase
from testsuites.certificate.certificate import (
    ComplianceFinding,
    ComplianceParameter,
    ComplianceReport,
    ComplianceStatus,
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
    finding = ComplianceFinding(test="Test receive FRBCSystemDescription")

    @S2TestCase.test
    async def test_receive_frbc_system_description(self):
        await self.wait_for_system_description()

        message = await self.check_receive_message_type(FRBCSystemDescription)

        self.test_logger.info("[SUCCESS] Test Receive FRBC System Description")


class FRBCActuatorStatusTestCase(FRBCTestCase):
    @S2TestCase.test
    async def test_receive_actuator_status(self):
        await self.wait_for_system_description()

        message = await self.check_receive_message_type(FRBCActuatorStatus)

        self.test_logger.info("[SUCCESS] Test Receive FRBC Actuator Status")


class FRBCStorageStatusTestCase(FRBCTestCase):
    finding = ComplianceFinding(test="Test receive FRBCStorageStatus")

    @S2TestCase.test
    async def test_receive_storage_status(self):
        await self.wait_for_system_description()

        message = await self.check_receive_message_type(FRBCStorageStatus)

        self.test_logger.info("[SUCCESS] Test Receive FRBC Storage Status")


class FRBCUsageForecastTestCase(FRBCTestCase):
    finding = ComplianceFinding(test="Test receive FRBCUsageForecast")

    @S2TestCase.test
    async def test_receive_usage_forecast(self):
        await self.wait_for_system_description()

        message = await self.check_receive_message_type(FRBCUsageForecast)

        self.test_logger.info("[SUCCESS] Test Receive FRBC Usage Forecast")
