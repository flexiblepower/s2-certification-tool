import abc
from testsuites.certificate.certificate import ComplianceReport, Signature


class AbstractCertifier(abc.ABC):

    @abc.abstractmethod
    def generate_signature(self, report: ComplianceReport) -> Signature:
        pass

    def sign_certificate(self, report: ComplianceReport) -> ComplianceReport:
        report.signature = self.generate_signature(report)

        return report


class MockCertifier(AbstractCertifier):

    def generate_signature(self, report: ComplianceReport) -> Signature:
        signature = Signature(server_signature="SOME SIGNATURE")
        return signature
