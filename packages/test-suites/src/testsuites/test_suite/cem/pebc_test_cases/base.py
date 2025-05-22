import logging
from connectivity.s2_channel import S2Channel

from connectivity.config import PEBCCEMTestConfig
from testsuites.certificate.certificate import ComplianceReport
from testsuites.controllers.cem.pebc_controller import PEBCCEMController
from testsuites.test_logger import TestLogger
from testsuites.test_suite.rm.base_test_case import NoSelectionTestCase
from testsuites.test_suite.test_suite import S2TestCase

logger = logging.getLogger(__name__)

from s2python.common import (
    ControlType as ProtocolControlType,
    EnergyManagementRole,
    PowerForecast,
    PowerMeasurement,
    PowerValue,
    ResourceManagerDetails,
    Handshake,
    NumberRange,
    Commodity,
    PowerRange,
    CommodityQuantity,
    Transition,
    Duration,
    RevokeObject,
)


class PEBCTestCase(S2TestCase):
    control_type = ProtocolControlType.POWER_ENVELOPE_BASED_CONTROL

    TIMEOUT = 5

    controller: PEBCCEMController
    config: PEBCCEMTestConfig

    def __init__(
        self,
        config: PEBCCEMTestConfig,
        channel: S2Channel,
        controller: PEBCCEMController,
        report: ComplianceReport,
        logger: TestLogger,
    ):
        super().__init__(config, channel, controller, report, logger)
