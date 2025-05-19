#!/usr/bin/env python

"""Echo server using the asyncio API."""

import argparse
import asyncio
import logging
import logging.config

from connectivity.config import Config, load_config
from log import get_log_config
from server import S2WebSocketClient, S2WebSocketServer
from server_side_certification_orchestrator import CertificationTestExecutor
from testsuites.certification_executor import AbstractCertificationExecutor
from testsuites.test_executor import create_test_executor
from testsuites.test_suite import TestLogger


parser = argparse.ArgumentParser(prog="S2 Self Cert")
parser.add_argument("config")
parser.add_argument(
    "-o", "--output", default="cert.yaml", help="Output file for the certificate."
)
parser.add_argument(
    "-l", "--log_file", default=None, help="Output file for the test suite logs."
)


logger = logging.getLogger(__name__)


def create_server_certification_executor(
    config: Config, test_logger: TestLogger
) -> CertificationTestExecutor:
    return CertificationTestExecutor(config, test_logger)


async def main():

    args = parser.parse_args()
    logging.config.dictConfig(get_log_config(args.log_file))

    config: Config = load_config(args.config)
    test_logger = TestLogger(logger=logging.getLogger("test-suite-logger"))

    if config.mode == "certification":
        test_executor = create_server_certification_executor(config, test_logger)
    elif config.mode == "testing":
        test_executor = create_test_executor(config, test_logger)
    else:
        raise ValueError("Invalid mode.")

    logger.info("-" * 40)
    logger.info(f"Starting in {config.mode} mode...")

    if config.connection.mode == "server":
        s2_server = S2WebSocketServer(
            config,
            test_executor,
            config.mode,
            args.output,
        )
        await s2_server.start()
    else:
        s2_client = S2WebSocketClient(
            config,
            test_executor,
            config.mode,
            args.output,
        )
        await s2_client.start()

    # report.export()


if __name__ == "__main__":
    asyncio.run(main())
