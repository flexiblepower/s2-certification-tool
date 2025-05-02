#!/usr/bin/env python

"""Echo server using the asyncio API."""

import argparse
import asyncio
from datetime import datetime
import logging
import logging.config
from typing import Dict

from s2python.common import ControlType as ProtocolControlType
from testsuites.certificate.certificate import ComplianceReport
from testsuites.config import Config, load_config
from testsuites.controllers import (
    Controller,
    BaseController,
    PEBCController,
    FRBCController,
)
from testsuites.test_executor import IntegrationTestExecutor
from testsuites.test_suite import PEBCTestCase, TestSuiteBuilder
from testsuites.test_suite.frbc_test_cases import FRBCTestCase
from log import LOGGING_CONFIG
from server import S2Server

# from server_side_certification_orchestrator import ServerSideCertificationOrchestrator

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


def create_local_test_orchestrator(config: Config) -> IntegrationTestExecutor:
    report = ComplianceReport(timestamp=datetime.now())

    controllers = create_controllers_dict_with_config(config, report)

    test_suite = (
        TestSuiteBuilder(config.control_types, report)
        .with_test_case(PEBCTestCase)
        .with_test_case(FRBCTestCase)
        .build()
    )

    orchestrator = IntegrationTestExecutor(
        available_control_types=controllers, test_suite=test_suite, report=report
    )

    return orchestrator


# def create_server_certification_orchestrator(config: Config) -> IntegrationTestExecutor:

#     return ServerSideCertificationOrchestrator()


async def main():

    args = parser.parse_args()

    config: Config = load_config(args.config)

    if config.mode == "certification":
        pass
        # orchestrator = create_server_certification_orchestrator(config)
    elif config.mode == "testing":
        test_executor = create_local_test_orchestrator(config)
    else:
        raise ValueError("Invalid mode.")

    logger.info("-" * 40)
    logger.info(f"Starting in {config.mode} mode...")

    s2_server = S2Server("0.0.0.0", 8000, test_executor, config.mode)

    await s2_server.start()

    # report.export()


if __name__ == "__main__":
    asyncio.run(main())
