#!/usr/bin/env python

"""Echo server using the asyncio API."""

import argparse
import asyncio
import logging
import logging.config

from connectivity.config import Config, load_config
from log import LOGGING_CONFIG
from server import S2WebSocketClient, S2WebSocketServer
from server_side_certification_orchestrator import CertificationTestExecutor
from testsuites.certification_executor import AbstractCertificationExecutor
from testsuites.test_executor import create_test_executor
from testsuites.test_suite import TestLogger

logging.config.dictConfig(LOGGING_CONFIG)

logger = logging.getLogger(__name__)

parser = argparse.ArgumentParser(prog="S2 Self Cert")
parser.add_argument("config")
parser.add_argument(
    "-o", "--output", default="cert.yaml", help="Output file for the certificate."
)


def create_server_certification_executor(config: Config) -> CertificationTestExecutor:
    return CertificationTestExecutor(
        config,
    )


async def main():

    args = parser.parse_args()

    config: Config = load_config(args.config)

    if config.mode == "certification":
        test_executor = create_server_certification_executor(config)
    elif config.mode == "testing":
        test_logger = TestLogger(logger=logging.getLogger("test-suite-logger"))
        test_executor = create_test_executor(config, test_logger)
    else:
        raise ValueError("Invalid mode.")

    logger.info("-" * 40)
    logger.info(f"Starting in {config.mode} mode...")

    if config.connection.mode == "server":
        s2_server = S2WebSocketServer(
            config.connection,
            test_executor,
            config.mode,
            args.output,
        )
        await s2_server.start()
    else:
        s2_client = S2WebSocketClient(
            config.connection,
            test_executor,
            config.mode,
            args.output,
        )
        await s2_client.start()

    # report.export()


if __name__ == "__main__":
    asyncio.run(main())
