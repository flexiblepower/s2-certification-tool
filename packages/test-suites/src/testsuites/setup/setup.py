import logging
import abc
import asyncio
from datetime import datetime
import logging
from typing import Dict, Optional
import uuid

from s2python.common import (
    ControlType as ProtocolControlType,
    EnergyManagementRole,
    Handshake,
    ResourceManagerDetails,
    CommodityQuantity,
    Currency,
    Duration,
    Role,
    RoleType,
    Commodity,
    SelectControlType,
)

from testsuites.test_executor import IntegrationTestExecutor
from testsuites.certificate.certificate import ComplianceReport
from .cem_tests import build_cem_test_suite
from .rm_tests import build_rm_test_suite
from testsuites.test_logger import (
    AbstractTestLogger,
)
from testsuites.controllers import (
    Controller,
    BaseRMController,
    # NotControllableRMController,
    PEBCRMController,
    FRBCRMController,
    BaseCEMController,
    NotControllableCEMController,
    FRBCCEMController,
    PEBCCEMController,
)

from testsuites.role_executors import (
    TestRoleExecutor,
    CEMTestRoleExecutor,
    RMTestExecutor,
)
from connectivity.config import Config, DeviceDetails

logger = logging.getLogger(__name__)


"""
This file contains the functions which assembles the IntegrationTestExecutor which is used 
by both the client side tester and the server side certifier.

The test case builder methods are located in this module as well.
"""

# Add all controllers to this list!
# As long as the role and control type value are set correctly they will be sorted
# The controllers will be loaded based on the config enabled field
controller_classes: list[type[Controller]] = [
    # Controllers used when testing an RM
    BaseRMController,
    FRBCRMController,
    PEBCRMController,
    # Controllers used when testing a CEM
    BaseCEMController,
    NotControllableCEMController,
    FRBCCEMController,
    PEBCCEMController,
]


def get_controller_classes_dict(role: EnergyManagementRole):
    classes = {}
    for controller_class in controller_classes:
        if controller_class.role == role:
            classes[controller_class.control_type] = controller_class
    return classes


def create_rm_controllers_dict_with_config(
    config: Config,
) -> Dict[ProtocolControlType, Controller]:
    """This method assembles the controllers dictionary for RM testing which the test executor uses to pick specific controllers."""
    controllers: Dict[ProtocolControlType, Controller] = {}

    controllers[ProtocolControlType.NO_SELECTION] = BaseRMController()

    # Load all of the enabled controllers based on config
    for control_type, controller_class in get_controller_classes_dict(
        EnergyManagementRole.RM
    ).items():
        try:
            control_type_config = config.roles.get_control_type_config(
                EnergyManagementRole.CEM, control_type
            )
            if control_type_config is not None and control_type_config.enabled:
                controllers[control_type] = controller_class()
        except KeyError:
            pass
    # if config.frbc and config.frbc.enabled:
    #     controllers[ProtocolControlType.FILL_RATE_BASED_CONTROL] = FRBCRMController()

    # if config.pebc and config.pebc.enabled:
    #     controllers[ProtocolControlType.POWER_ENVELOPE_BASED_CONTROL] = (
    #         PEBCRMController()
    #     )

    return controllers


def create_rm_details(details: DeviceDetails):
    return ResourceManagerDetails(
        available_control_types=[
            ProtocolControlType.NOT_CONTROLABLE
        ],  # I'll set this based on the controllers dict
        roles=[
            Role(
                role=RoleType.ENERGY_PRODUCER,
                commodity=Commodity.ELECTRICITY,
            )
        ],
        name=details.name,
        manufacturer=details.manufacturer,
        model=details.model,
        firmware_version=details.firmware_version,
        serial_number=details.serial_number,
        currency=details.currency,
        message_id=uuid.uuid4(),
        resource_id=uuid.uuid4(),
        # TODO: These should probably be determined by the test case somehow...
        provides_forecast=True,
        provides_power_measurement_types=[CommodityQuantity.ELECTRIC_POWER_L1],
        instruction_processing_delay=Duration(0),
    )


def create_cem_controllers_dict_with_config(
    config: Config,
) -> Dict[ProtocolControlType, Controller]:
    """This method assembles the controllers dictionary for CEM testing which the test executor uses to pick specific controllers."""

    rm_details = create_rm_details(config.device_details)

    controllers: Dict[ProtocolControlType, Controller] = {}
    controllers[ProtocolControlType.NO_SELECTION] = BaseCEMController(rm_details)

    # Load all of the enabled controllers based on config
    for control_type, controller_class in get_controller_classes_dict(
        EnergyManagementRole.CEM
    ).items():
        try:
            control_type_config = config.roles.get_control_type_config(
                EnergyManagementRole.CEM, control_type
            )
            if control_type_config is not None and control_type_config.enabled:
                controllers[control_type] = controller_class(rm_details)
        except KeyError:
            pass

    # Set the Available Control Types based on the config and available controllers
    control_type_set = set(controllers.keys())
    control_type_set.discard(ProtocolControlType.NO_SELECTION)
    rm_details.available_control_types = list(control_type_set)

    return controllers


def create_test_executor(
    config: Config, test_logger: AbstractTestLogger
) -> IntegrationTestExecutor:
    report = ComplianceReport(timestamp=datetime.now(), device=config.device_details)

    rm_controllers = create_rm_controllers_dict_with_config(config)

    rm_test_suite_builder = build_rm_test_suite(config, report, test_logger)
    rm_role_executor = RMTestExecutor(
        available_control_types=rm_controllers,
        test_suite=rm_test_suite_builder.build(),
        report=report,
        test_logger=test_logger,
    )

    cem_controllers = create_cem_controllers_dict_with_config(config)
    cem_test_suite_builder = build_cem_test_suite(config, report, test_logger)
    cem_role_executor = CEMTestRoleExecutor(
        controllers=cem_controllers,
        test_suite=cem_test_suite_builder.build(),
        report=report,
        test_logger=test_logger,
    )

    role_executors: Dict[EnergyManagementRole, TestRoleExecutor] = {
        EnergyManagementRole.RM: rm_role_executor,
        EnergyManagementRole.CEM: cem_role_executor,
    }

    # The main integration test class. Everything to do with testing is encapsulated in it!
    return IntegrationTestExecutor(role_executors=role_executors)
