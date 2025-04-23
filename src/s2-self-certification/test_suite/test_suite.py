import abc
import logging
from typing import TYPE_CHECKING, Dict, List, Type

from config import BaseTestConfig, ControlTypeTestConfig
from connection import Connection
from controllers.controller import Controller
from s2python.common import ControlType as ProtocolControlType

logger = logging.getLogger(__name__)


class S2TestCase(abc.ABC):
    control_type: ProtocolControlType = ProtocolControlType.NO_SELECTION
    config: BaseTestConfig

    def __init__(
        self,
        config: BaseTestConfig,
        connection: Connection,
        controller: Controller,
    ):
        self.connection = connection
        self.controller = controller
        self.config = config

    @abc.abstractmethod
    def execute(self):
        pass


class TestSuite:
    config: ControlTypeTestConfig
    test_cases: Dict[ProtocolControlType, List[Type[S2TestCase]]]

    def __init__(self, config: ControlTypeTestConfig):
        self.test_cases = {}
        self.config = config

    def add_test_case(self, test_case: Type[S2TestCase]):
        if test_case.control_type in self.test_cases:
            self.test_cases[test_case.control_type].append(test_case)
        else:
            self.test_cases[test_case.control_type] = [test_case]

    async def execute(self, connection: Connection, controller: Controller):
        self.controller = controller
        self.connection = connection

        control_type = controller.control_type

        for TestCase in self.test_cases.get(control_type, []):
            control_type = TestCase.control_type
            test_case = TestCase(
                self.config.get_control_type_config(control_type),
                connection,
                controller,
            )
            test_case.execute()


class TestSuiteBuilder:
    def __init__(self, config: ControlTypeTestConfig):
        self.test_suite = TestSuite(config)

    def with_test_case(self, test_case):
        self.test_suite.add_test_case(test_case)
        return self

    def build(self):
        return self.test_suite
