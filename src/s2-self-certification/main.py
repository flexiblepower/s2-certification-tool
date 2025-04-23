#!/usr/bin/env python

"""Echo server using the asyncio API."""

import argparse
import asyncio
import logging
import logging.config
from typing import Dict

from config import Config, load_config
from controllers import Controller, PEBCController, FRBCController
from log import LOGGING_CONFIG
from orchestrator import IntegrationTestOrchestrator
from s2python.common import ControlType as ProtocolControlType
from server import S2Server
from test_suite import PEBCTestCase, TestSuiteBuilder
from test_suite.frbc_test_cases import FRBCTestCase

logging.config.dictConfig(LOGGING_CONFIG)

logging.getLogger("websockets").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)

parser = argparse.ArgumentParser(prog="S2 Self Cert")
parser.add_argument("config")


async def main():
    logger.info("-" * 40)
    logger.info("Starting...")

    args = parser.parse_args()

    config: Config = load_config(args.config)

    control_types: Dict[ProtocolControlType, Controller] = {
        ProtocolControlType.POWER_ENVELOPE_BASED_CONTROL: PEBCController(),
        ProtocolControlType.FILL_RATE_BASED_CONTROL: FRBCController(),
    }

    test_suite = (
        TestSuiteBuilder(config.control_types)
        .with_test_case(PEBCTestCase)
        .with_test_case(FRBCTestCase)
        .build()
    )

    orchestrator = IntegrationTestOrchestrator(
        available_control_types=control_types, test_suites=test_suite
    )

    s2_server = S2Server("0.0.0.0", 8000, orchestrator)
    await s2_server.start()


if __name__ == "__main__":
    asyncio.run(main())
