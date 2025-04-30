import uuid
from typing import List
from typing_extensions import Self

from pydantic import model_validator

from s2python.generated.gen_s2 import (
    PEBCPowerConstraints as GenPEBCPowerConstraints,
    PEBCPowerEnvelopeConsequenceType as GenPEBCPowerEnvelopeConsequenceType,
    PEBCPowerEnvelopeLimitType,
)
from s2python.pebc.pebc_allowed_limit_range import PEBCAllowedLimitRange
from s2python.validate_values_mixin import (
    catch_and_convert_exceptions,
    S2MessageComponent,
)


@catch_and_convert_exceptions
class PEBCPowerConstraints(GenPEBCPowerConstraints, S2MessageComponent):
    model_config = GenPEBCPowerConstraints.model_config
    model_config["validate_assignment"] = True

    message_id: uuid.UUID = GenPEBCPowerConstraints.model_fields["message_id"]  # type: ignore[assignment,reportIncompatibleVariableOverride]
    id: uuid.UUID = GenPEBCPowerConstraints.model_fields["id"]  # type: ignore[assignment,reportIncompatibleVariableOverride]
    consequence_type: GenPEBCPowerEnvelopeConsequenceType = GenPEBCPowerConstraints.model_fields[  # type: ignore[reportIncompatibleVariableOverride]
        "consequence_type"
    ]  # type: ignore[assignment]
    allowed_limit_ranges: List[PEBCAllowedLimitRange] = GenPEBCPowerConstraints.model_fields[  # type: ignore[reportIncompatibleVariableOverride]
        "allowed_limit_ranges"
    ]  # type: ignore[assignment]

    @model_validator(mode="after")
    def validate_has_one_upper_one_lower_limit_range(self) -> Self:
        has_upper = any(
            l.limit_type == PEBCPowerEnvelopeLimitType.UPPER_LIMIT
            for l in self.allowed_limit_ranges
        )
        has_lower = any(
            l.limit_type == PEBCPowerEnvelopeLimitType.UPPER_LIMIT
            for l in self.allowed_limit_ranges
        )
        if not (has_upper and has_lower):
            raise ValueError(
                self,
                f"There shall be at least one PEBC.AllowedLimitRange for the UPPER_LIMIT and at least one AllowedLimitRange for the LOWER_LIMIT.",
            )

        return self

    @model_validator(mode="after")
    def validate_valid_until_after_valid_from(self) -> Self:
        if self.valid_until is not None and self.valid_until < self.valid_from:
            raise ValueError(
                self, f"valid_until cannot be set to a value that is before valid_from."
            )
        return self
