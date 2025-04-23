import datetime
import logging
import uuid

from config import FRBCTestConfig, PEBCTestConfig
from connection import Connection
from controllers.frbc_controller import FRBCController
from s2python.common import PowerMeasurement
from s2python.pebc import (
    PEBCAllowedLimitRange,
    PEBCInstruction,
    PEBCPowerEnvelope,
    PEBCPowerEnvelopeElement,
)
from test_suite.test_suite import S2TestCase

logger = logging.getLogger(__name__)


class FRBCTestCase(S2TestCase):

    controller: FRBCController
    config: FRBCTestConfig

    def __init__(
        self,
        config: FRBCTestConfig,
        connection: Connection,
        controller: FRBCController,
    ):
        super().__init__(config, connection, controller)
