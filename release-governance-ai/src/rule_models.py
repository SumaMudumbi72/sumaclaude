"""Domain models for deterministic governance rules."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class RuleStatus(str, Enum):
    """Outcome of one governance rule evaluation."""

    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"


class OverallDecision(str, Enum):
    """Final recommendation for a release."""

    PROCEED = "PROCEED"
    CONDITIONAL_APPROVAL = "CONDITIONAL APPROVAL"
    BLOCK = "BLOCK"
    ESCALATE = "ESCALATE"


@dataclass(frozen=True)
class RuleDefinition:
    """One configurable governance rule."""

    name: str
    field: str | None = None
    operator: str = "gt"
    value: Any = None
    description: str | None = None
    recommendation: str = ""
    outcome: str = "BLOCK"
    warning: bool = False
    mandatory: bool = True


GovernanceRule = RuleDefinition
Rule = RuleDefinition

__all__ = [
    "OverallDecision",
    "Rule",
    "RuleDefinition",
    "RuleStatus",
    "GovernanceRule",
]
