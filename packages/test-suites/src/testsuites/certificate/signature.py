import abc
import asyncio
import base64
import os
from typing import Optional
from testsuites.certificate.certificate import ComplianceReport, Signature
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.exceptions import InvalidSignature
from testsuites.message_handlers import CertificationMessageHandler
import yaml
from connectivity.channel import Channel
from testsuites.envelope_models import (
    ServerMessageEnvelope,
    CertificationEnvelope,
    CertificationMessageType,
    KeyRegistrationRequestMessage,
    ChallengeMessage,
    ChallengeProofMessage,
    ChallengeStatusMessage,
    CertificationMessage,
    parse_certification_message,
)

import logging

logger = logging.getLogger(__name__)


class SimpleCertifier:
    """This class is responsible for signing with a given PEM private key."""

    def __init__(self, key_path: str, key_pass: Optional[bytes] = None) -> None:
        self.load_key(key_path, key_pass)

    def get_public_key(self):
        if self.private_key is None:
            raise ValueError("Private Key must be provided.")
        return self.private_key.public_key()

    def get_serialized_public_key(self) -> bytes:
        public_key = self.get_public_key()
        pem_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        return pem_bytes

    def load_key(self, key_path: str, key_pass: Optional[bytes] = None):
        if not os.path.exists(key_path):
            raise ValueError("Invalid Key Path.")

        with open(key_path, "rb") as key_file:
            self.private_key = serialization.load_pem_private_key(
                key_file.read(), password=key_pass
            )

    def sign_bytes(self, data: bytes) -> bytes:
        signature = self.private_key.sign(  # type: ignore
            data,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH
            ),  # type: ignore
            hashes.SHA256(),  # type: ignore
        )
        return signature

    def verify_bytes(self, signature: bytes, data: bytes, public_key=None) -> bool:
        # Use provided public key or default to our private key's public key
        if public_key is None:
            public_key = self.get_public_key()

        try:
            public_key.verify(  # type: ignore
                signature,
                data,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH,
                ),  # type: ignore
                hashes.SHA256(),  # type: ignore
            )
            return True
        except InvalidSignature:
            return False

    @staticmethod
    def load_public_key_from_pem(pem_string: str):
        """Load a public key from PEM string format"""
        return serialization.load_pem_public_key(pem_string.encode("utf-8"))


class ReportSigner(SimpleCertifier):

    def get_bytes_to_sign(self, report: ComplianceReport) -> bytes:
        report_copy = report.model_copy()

        # Remove signature in the case of verifying
        if report_copy.signature is not None:
            report_copy.signature = None

        report_dict = report_copy.generate_certificate_dict()
        yaml_bytes = yaml.dump(report_dict, sort_keys=True).encode("utf-8")

        return yaml_bytes

    def generate_report_signature(self, report: ComplianceReport) -> Signature:
        yaml_bytes = self.get_bytes_to_sign(report)

        signature = self.sign_bytes(yaml_bytes)

        report_signature = Signature(server_signature=signature.hex())

        return report_signature

    def sign_report(self, report: ComplianceReport):
        report.signature = self.generate_report_signature(report)
        return report

    def verify_signature(self, report: ComplianceReport) -> bool:

        if report.signature is None or report.signature.server_signature is None:
            raise ValueError("No signature to verify.")

        yaml_bytes = self.get_bytes_to_sign(report)
        signature = bytes.fromhex(report.signature.server_signature)

        return self.verify_bytes(signature, yaml_bytes)


class CertificationEncoder:

    @classmethod
    def encode(cls, data: bytes) -> str:
        return base64.b64encode(data).decode("ascii")

    @classmethod
    def decode(cls, data: str) -> bytes:
        return base64.b64decode(data)
