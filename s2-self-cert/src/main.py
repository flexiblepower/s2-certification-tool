#!/usr/bin/env python

"""Echo server using the asyncio API."""

import argparse
import asyncio
import logging
import logging.config

from connectivity.config import Config, load_config
from log import LOGGING_CONFIG
from server import S2Server
from server_side_certification_orchestrator import CertificationTestExecutor
from testsuites.certification_executor import AbstractCertificationExecutor
from testsuites.test_executor import create_test_executor

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
        test_executor = create_test_executor(config)
    else:
        raise ValueError("Invalid mode.")

    logger.info("-" * 40)
    logger.info(f"Starting in {config.mode} mode...")

    s2_server = S2Server("0.0.0.0", 8000, test_executor, config.mode, args.output)

    await s2_server.start()

    # report.export()


if __name__ == "__main__":
    asyncio.run(main())
