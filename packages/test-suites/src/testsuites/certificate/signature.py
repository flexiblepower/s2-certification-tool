import base64
from datetime import datetime
import os
from typing import Optional
from testsuites.certificate.certificate import ComplianceReport
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.exceptions import InvalidSignature
import yaml

import logging

logger = logging.getLogger(__name__)


class CertificationEncoder:
    # Centralize encoding and decoding from bytes to allow for it to be changed later
    # Currently uses Base 64
    # ALL ENCODING AND DECODING WITH BYTES SHOULD USE THIS - Facilitates easily swapping it out.

    @classmethod
    def encode(cls, data: bytes) -> str:
        return base64.b64encode(data).decode("ascii")

    @classmethod
    def decode(cls, data: str) -> bytes:
        return base64.b64decode(data)


class SimpleCertifier:
    """This class is responsible for signing with a given PEM private key."""

    PADDING = padding.PSS(
        mgf=padding.MGF1(hashes.SHA256()),
        salt_length=padding.PSS.MAX_LENGTH,
    )
    ALGORITHM = hashes.SHA256()

    SERIALIZATION_ENCODING = serialization.Encoding.PEM
    SERIALIZATION_FORMAT = serialization.PublicFormat.SubjectPublicKeyInfo

    def __init__(self, key_path: str, key_pass: Optional[bytes] = None) -> None:
        self.load_key(key_path, key_pass)

    def get_public_key(self):
        """Gets the public key from the private key that was loaded."""

        if self.private_key is None:
            raise ValueError("Private Key must be provided.")
        return self.private_key.public_key()

    def get_serialized_public_key(self) -> bytes:
        public_key = self.get_public_key()
        pem_bytes = public_key.public_bytes(
            encoding=self.SERIALIZATION_ENCODING,
            format=self.SERIALIZATION_FORMAT,
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
        """Performs the signing of some byte data using the loaded private key."""
        signature = self.private_key.sign(  # type: ignore
            data,
            self.PADDING,  # type: ignore
            self.ALGORITHM,  # type: ignore
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
                self.PADDING,  # type: ignore
                self.ALGORITHM,  # type: ignore
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
        report_dict = report.generate_certificate_dict()
        yaml_bytes = yaml.dump(report_dict, sort_keys=True).encode("utf-8")

        return yaml_bytes

    def generate_report_signature(self, report: ComplianceReport) -> str:
        yaml_bytes = self.get_bytes_to_sign(report)

        signature = self.sign_bytes(yaml_bytes)

        return CertificationEncoder.encode(signature)

    def verify(self, report: ComplianceReport, signature: str, public_key=None) -> bool:
        yaml_bytes = self.get_bytes_to_sign(report)
        signature_bytes = CertificationEncoder.decode(signature)

        return self.verify_bytes(signature_bytes, yaml_bytes, public_key=public_key)

    def verify_client_signed(
        self, report: ComplianceReport, client_id: str, client_public_key=None
    ) -> bool:
        logger.info(client_public_key)
        report_copy = report.model_copy(deep=True)
        if report_copy.signature.client_signature is None:
            return False

        if report_copy.signature.client_id != client_id:
            return False

        client_signature = report_copy.signature.client_signature

        # Clear it so that the certificate will be correct
        report_copy.signature.client_signature = None
        report_copy.signature.server_signature = None
        report_copy.signature.server_signature_timestamp = None

        result = self.verify(report_copy, client_signature, client_public_key)
        return result

    def verify_double_signed(
        self, report: ComplianceReport, client_id: str, client_public_key=None
    ) -> bool:
        """Verifies that the report is double signed by both the server and the client certificate."""
        report_copy = report.model_copy(deep=True)
        if (
            report_copy.signature.client_signature is None
            or report_copy.signature.server_signature is None
        ):
            logger.warning("Both signatures must be present to verify double signed.")
            return False

        if report_copy.signature.client_id != client_id:
            logger.warning("Client IDs don't match.")
            return False

        server_signature = report_copy.signature.server_signature
        report_copy.signature.server_signature = None

        logger.info("Verifying server signature...")

        server_signature_valid = self.verify(
            report_copy, server_signature, self.get_public_key()
        )

        if not server_signature_valid:
            logger.warning("Server signature is not valid.")
            return False
        logger.warning("Server signature is valid. Verifying client signature...")

        client_signature_valid = self.verify_client_signed(
            report_copy, client_id, client_public_key
        )

        if not client_signature_valid:
            logger.warning("Client signature is not valid.")
        return client_signature_valid


class ClientReportSigner(ReportSigner):

    def sign_report(self, report: ComplianceReport):
        """Single Signs the report with the client key"""
        report.signature.server_signature = None
        report.signature.server_signature_timestamp = None
        report.signature.client_signature = None

        if report.signature.client_id is None:
            raise ValueError("Client ID must be included in the signature.")

        # Include the datatime in the content to be signed
        report.signature.client_signature_timestamp = datetime.now()
        report.signature.client_signature = self.generate_report_signature(report)

        return report


class ServerReportSigner(ReportSigner):

    def sign_report(self, report: ComplianceReport, client_id: str):
        """Double signs a report, provided that it's already been signed by the client."""

        if (
            report.signature.client_signature is None
            or report.signature.client_signature_timestamp is None
            or report.signature.client_id is None
            or report.signature.client_id != client_id
        ):
            raise ValueError(
                "Report must first be signed by the client and the client IDs must match.."
            )

        report.signature.server_signature = None
        report.signature.server_signature_timestamp = datetime.now()

        report.signature.server_signature = self.generate_report_signature(report)

        return report
