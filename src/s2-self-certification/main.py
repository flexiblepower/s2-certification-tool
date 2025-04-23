#!/usr/bin/env python

"""Echo server using the asyncio API."""

import argparse
import asyncio
import logging
import logging.config
import sys
from typing import Dict
from orchestrator import IntegrationTestOrchestrator
from server import S2Server

from message_handlers import (
    Controller,
    PEBCController,
)
from s2python.common import ControlType as ProtocolControlType
from test_suite import build_test_suite
from log import LOGGING_CONFIG
from config import Config, load_config

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
        ProtocolControlType.POWER_ENVELOPE_BASED_CONTROL: PEBCController(
            config.control_types.pebc
        ),
        # ProtocolControlType.FILL_RATE_BASED_CONTROL: create_frbc_handler_manager(),
    }

    test_suite = build_test_suite()

    controller = IntegrationTestOrchestrator(
        available_control_types=control_types, test_suite=test_suite
    )

    s2_server = S2Server("0.0.0.0", 8000, controller)
    await s2_server.start()


if __name__ == "__main__":
    asyncio.run(main())
