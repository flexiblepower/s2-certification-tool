#!/usr/bin/env python

"""Echo server using the asyncio API."""

import argparse
import asyncio
import logging
import logging.config

from connectivity.config import Config, load_config
from s2selfcert.log import get_log_config
from s2selfcert.server import S2WebSocketClient, S2WebSocketServer
from s2selfcert.server_side_certification_orchestrator import CertificationTestExecutor
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


class OnCompleteCallback:
    config: Config

    def __init__(self, config: Config):
        self.config = config

    async def __call__(self, executor: AbstractCertificationExecutor):
        report = await executor.get_compliance_report()
        report.export(self.config.report)


async def run_application(args):

    try:
        logging.config.dictConfig(get_log_config(args.log_file))
    except Exception as e:
        print(e)
        return

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

    callback = OnCompleteCallback(config)

    if config.connection.mode == "server":
        s2_server = S2WebSocketServer(
            config.connection,
            test_executor,
            callback,
            config.mode,
        )
        await s2_server.start()
    else:
        s2_client = S2WebSocketClient(
            config.connection,
            test_executor,
            callback,
            config.mode,
        )
        await s2_client.start()

    # report.export()


def main():
    args = parser.parse_args()
    asyncio.run(run_application(args))


if __name__ == "__main__":
    main()
