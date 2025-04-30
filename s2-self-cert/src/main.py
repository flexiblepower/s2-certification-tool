#!/usr/bin/env python

"""Echo server using the asyncio API."""

import argparse
import asyncio
from datetime import datetime
import logging
import logging.config
from typing import Dict

from s2python.common import ControlType as ProtocolControlType
from s2testing.certificate.certificate import ComplianceReport
from s2testing.config import Config, load_config
from s2testing.controllers import (
    Controller,
    BaseController,
    PEBCController,
    FRBCController,
)
from s2testing.orchestrator import IntegrationTestOrchestrator
from s2testing.test_suite import PEBCTestCase, TestSuiteBuilder
from s2testing.test_suite.frbc_test_cases import FRBCTestCase
from log import LOGGING_CONFIG
from server import S2Server

logging.config.dictConfig(LOGGING_CONFIG)

logger = logging.getLogger(__name__)

parser = argparse.ArgumentParser(prog="S2 Self Cert")
parser.add_argument("config")


def create_controllers_dict_with_config(
    config: Config, report: ComplianceReport
) -> Dict[ProtocolControlType, Controller]:
    controllers: Dict[ProtocolControlType, Controller] = {}

    controllers[ProtocolControlType.NO_SELECTION] = BaseController()

    if config.control_types.frbc and config.control_types.frbc.enabled:
        controllers[ProtocolControlType.FILL_RATE_BASED_CONTROL] = FRBCController()

    if config.control_types.pebc and config.control_types.pebc.enabled:
        controllers[ProtocolControlType.POWER_ENVELOPE_BASED_CONTROL] = PEBCController()

    return controllers


async def main():

    args = parser.parse_args()

    config: Config = load_config(args.config)

    logger.info("-" * 40)
    logger.info(f"Starting in {config.mode} mode...")

    report = ComplianceReport(timestamp=datetime.now())

    controllers = create_controllers_dict_with_config(config, report)

    test_suite = (
        TestSuiteBuilder(config.control_types, report)
        .with_test_case(PEBCTestCase)
        .with_test_case(FRBCTestCase)
        .build()
    )

    orchestrator = IntegrationTestOrchestrator(
        available_control_types=controllers, test_suite=test_suite, report=report
    )

    s2_server = S2Server("0.0.0.0", 8000, orchestrator)

    await s2_server.start()

    report.export()


if __name__ == "__main__":
    asyncio.run(main())
