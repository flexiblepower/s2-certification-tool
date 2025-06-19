#!/usr/bin/env python

"""Echo server using the asyncio API."""

import argparse
import asyncio
import logging
import logging.config
import os

from connectivity.config import Config, load_config, ConfigError
from pydantic import ValidationError
import yaml
from s2selfcert.certifier import ClientSideCertifier
from s2selfcert.log import get_log_config
from s2selfcert.server import S2WebSocketClient, S2WebSocketServer
from s2selfcert.server_side_certification_orchestrator import CertificationTestExecutor
from testsuites.certification_executor import AbstractCertificationExecutor
from testsuites.setup import create_test_executor
from testsuites.test_suite import TestLogger
from testsuites.certificate.signature import SimpleCertifier, ClientReportSigner
from testsuites.util import pretty_print_pydantic_validation_error

CONFIG_PATH = os.environ.get("CONFIG_PATH", None)

parser = argparse.ArgumentParser(prog="S2 Self Cert")
parser.add_argument("-c", "--config", default=None)

logger = logging.getLogger(__name__)


def create_server_certification_executor(
    config: Config, test_logger: TestLogger
) -> CertificationTestExecutor:
    # openssl genpkey -algorithm RSA -out server_key.pem -pkeyopt rsa_keygen_bits:2048
    if config.certification is None:
        raise ConfigError(
            "Private Key path, Client ID and Certification server URI must be supplied when in certification mode."
        )

    signer = ClientReportSigner(config.certification.key_path)
    certification_handler = ClientSideCertifier("something", signer)
    return CertificationTestExecutor(config, test_logger, certification_handler)


class OnCompleteCallback:
    # When the test executor completes this callback is triggered to perform any cleanup or final output
    # Currently this exports the report
    config: Config

    def __init__(self, config: Config):
        self.config = config

    async def __call__(self, executor: AbstractCertificationExecutor):
        logger.info("Callback executed.")
        report = await executor.get_compliance_report()
        report.export(self.config.report)


async def run_application(args):

    try:
        # The log file is where the test logs will be written to. This applies to both local testing and remote certification!
        logging.config.dictConfig(get_log_config())
    except Exception as e:
        print(e)
        return

    if args.config is not None:
        config_path = args.config
    elif CONFIG_PATH is not None:
        config_path = CONFIG_PATH
    else:
        logger.error(
            "Config path must be provided! This can be done using the command param or with the CONFIG_PATH env var."
        )
        return

    # Load the config
    try:
        config: Config = load_config(config_path)
    except yaml.YAMLError as exc:
        logger.error(f"Failed to load config from YAML file. Is it: {exc}")
        return
    except ValidationError as exc:
        logger.error(
            "Failed to load config due to validation errors:\n%s",
            pretty_print_pydantic_validation_error(exc),
        )
        return

    # Reload log config since we now know if we need to write a test log.
    logging.config.dictConfig(get_log_config(config.report.log_path))

    # Setup the test logger wrapper.
    # This wrapper is what allows for logging to come back in server certification mode
    # When in certification mode log messages are passed to the logger instance passed as a param
    test_logger = TestLogger(logger=logging.getLogger("test-suite-logger"))

    # Setup the executor depending on the mode set in the config
    if config.mode == "certification":
        test_executor = create_server_certification_executor(config, test_logger)
    elif config.mode == "testing":
        test_executor = create_test_executor(config, test_logger)
    else:
        raise ValueError("Invalid mode.")

    logger.info("-" * 40)
    logger.info(f"Starting in {config.mode} mode.")

    # Setup the callback which is run once the session is complete. In this case it exports the certificate to a file.
    callback = OnCompleteCallback(config)

    # Startup happens in different ways depending on the connection code
    # 1. Server will listen on a specified port and host for incoming S2 Device Connections
    # 2. Client will create an outgoing websocket connection to a S2 Device
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


def main():
    args = parser.parse_args()
    asyncio.run(run_application(args))


if __name__ == "__main__":
    main()
