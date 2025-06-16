import pytest
import secrets

from testsuites.certificate.certificate import (
    ComplianceReport,
    Signature,
    DeviceDetails,
)

from src.certifier import ReportSigner

certifier = ReportSigner("./server_key.pem")


def generate_test_report():
    device_details = DeviceDetails(name="Test", manufacturer="Test Manufacturer")

    return ComplianceReport(device=device_details)


def test_simple_certifier():
    # Check that the certifier can sign and verify a certificate successfully
    report = generate_test_report()

    report = certifier.sign_report(report)

    assert report.signature is not None

    valid = certifier.verify_signature(report)

    assert valid


def test_simple_certifier_already_has_signature():
    # Check that the old signature is replaced with a new, correct one
    report = generate_test_report()
    report.signature = Signature(server_signature="SOME SIGNATURE")

    report = certifier.sign_report(report)

    assert report.signature is not None

    valid = certifier.verify_signature(report)

    assert valid


def test_verify_fails():
    report = generate_test_report()
    # Generate random hex since the certifier requires hex data
    report.signature = Signature(server_signature=secrets.token_hex())

    valid = certifier.verify_signature(report)

    assert not valid
