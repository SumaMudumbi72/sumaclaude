"""Pydantic models for release-governance data and configuration.

Data models describe the JSON datasets under ``data/``. Configuration models
describe the YAML files under ``config/``. All timestamps must include a
timezone (e.g. ``2026-10-20T02:00:00Z``) so comparisons are unambiguous.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeInt,
    ValidationError,
    field_validator,
    model_validator,
)

# Identifier formats shared by several models.
RELEASE_ID_PATTERN = r"^REL-\d{4}\.\d{2}(\.\d+)?$"
APPLICATION_ID_PATTERN = r"^APP-[A-Z0-9-]+$"
VERSION_PATTERN = r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$"
COMMIT_SHA_PATTERN = r"^[0-9a-f]{7,40}$"


# --------------------------------------------------------------------------
# Enumerations
# --------------------------------------------------------------------------


class Environment(StrEnum):
    """Deployment environments a release or freeze window can target."""

    DEVELOPMENT = "DEVELOPMENT"
    QA = "QA"
    STAGING = "STAGING"
    PRODUCTION = "PRODUCTION"


class ReleaseStatus(StrEnum):
    """Lifecycle state of a release."""

    PLANNED = "PLANNED"
    IN_DEVELOPMENT = "IN_DEVELOPMENT"
    IN_TESTING = "IN_TESTING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    DEPLOYED = "DEPLOYED"
    ROLLED_BACK = "ROLLED_BACK"
    CANCELLED = "CANCELLED"

    @property
    def is_terminal(self) -> bool:
        """Whether the release has finished its lifecycle."""
        return self in {ReleaseStatus.DEPLOYED, ReleaseStatus.ROLLED_BACK, ReleaseStatus.CANCELLED}


class Criticality(StrEnum):
    """Business criticality tier of an application (TIER_1 is most critical)."""

    TIER_1 = "TIER_1"
    TIER_2 = "TIER_2"
    TIER_3 = "TIER_3"


class Severity(StrEnum):
    """Defect severity, from most to least serious."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class DefectStatus(StrEnum):
    """Workflow state of a defect."""

    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    REOPENED = "REOPENED"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    DEFERRED = "DEFERRED"

    @property
    def is_open(self) -> bool:
        """Whether the defect still needs work before release.

        ``DEFERRED`` counts as not open: it was explicitly accepted for a
        later release.
        """
        return self in {DefectStatus.OPEN, DefectStatus.IN_PROGRESS, DefectStatus.REOPENED}


class PipelineStatus(StrEnum):
    """Outcome of a CI/CD pipeline run or stage."""

    SUCCESS = "SUCCESS"
    UNSTABLE = "UNSTABLE"
    RUNNING = "RUNNING"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class ApprovalRole(StrEnum):
    """Roles that sign off on a release."""

    QA_LEAD = "QA_LEAD"
    SECURITY = "SECURITY"
    PRODUCT_OWNER = "PRODUCT_OWNER"
    CHANGE_ADVISORY_BOARD = "CHANGE_ADVISORY_BOARD"
    ENGINEERING_MANAGER = "ENGINEERING_MANAGER"
    OPERATIONS = "OPERATIONS"


class ApprovalStatus(StrEnum):
    """Decision state of an approval."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class FreezeType(StrEnum):
    """How strictly a freeze window restricts changes."""

    HARD = "HARD"  # No changes without executive exception.
    SOFT = "SOFT"  # Changes allowed with extra approval.


class ReleaseOutcome(StrEnum):
    """Result of a past production release."""

    SUCCESS = "SUCCESS"
    HOTFIX_REQUIRED = "HOTFIX_REQUIRED"
    ROLLED_BACK = "ROLLED_BACK"
    FAILED = "FAILED"


# --------------------------------------------------------------------------
# Base classes
# --------------------------------------------------------------------------


class GovernanceModel(BaseModel):
    """Base for all data models.

    Records are immutable once loaded. Unknown fields are ignored so that
    richer exports from source systems still load.
    """

    model_config = ConfigDict(frozen=True, extra="ignore", str_strip_whitespace=True)


class ConfigModel(BaseModel):
    """Base for configuration models.

    Unknown keys are rejected so that typos in YAML files are caught early.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


def format_validation_errors(exc: ValidationError) -> list[str]:
    """Turn a pydantic error into readable ``field.path: message`` strings.

    Args:
        exc: The error raised by ``model_validate``.

    Returns:
        One message per failed rule.
    """
    return [
        f"{'.'.join(str(part) for part in error['loc']) or '<record>'}: {error['msg']}"
        for error in exc.errors()
    ]


def _ensure_not_before(start: datetime, end: datetime | None, start_name: str, end_name: str) -> None:
    """Raise ``ValueError`` if ``end`` is set and earlier than ``start``."""
    if end is not None and end < start:
        raise ValueError(f"{end_name} must not be earlier than {start_name}")


# --------------------------------------------------------------------------
# Release and applications
# --------------------------------------------------------------------------


class Application(GovernanceModel):
    """An application (deployable component) included in a release."""

    app_id: str = Field(pattern=APPLICATION_ID_PATTERN, description="Unique ID, e.g. APP-PAYMENTS")
    name: str = Field(min_length=1, max_length=120)
    version: str = Field(pattern=VERSION_PATTERN, description="Version shipped in this release")
    owner_team: str = Field(min_length=1)
    criticality: Criticality = Criticality.TIER_2
    # Optional list of services or modules changed in this release.
    components: list[str] = Field(default_factory=list)


class Release(GovernanceModel):
    """A planned or completed software release covering one or more applications."""

    release_id: str = Field(pattern=RELEASE_ID_PATTERN, description="e.g. REL-2026.10")
    name: str = Field(min_length=1, max_length=200)
    version: str = Field(pattern=VERSION_PATTERN)
    target_date: AwareDatetime = Field(description="Planned production deployment time")
    environment: Environment = Environment.PRODUCTION
    status: ReleaseStatus = ReleaseStatus.PLANNED
    release_manager: str = Field(min_length=1)
    applications: list[Application] = Field(min_length=1)
    description: str | None = None
    change_ticket: str | None = Field(default=None, description="Change-management reference")

    @field_validator("applications")
    @classmethod
    def _unique_application_ids(cls, applications: list[Application]) -> list[Application]:
        """Reject releases that list the same application twice."""
        ids = [app.app_id for app in applications]
        duplicates = sorted({app_id for app_id in ids if ids.count(app_id) > 1})
        if duplicates:
            raise ValueError(f"duplicate application IDs: {', '.join(duplicates)}")
        return applications

    @property
    def application_ids(self) -> set[str]:
        """IDs of all applications in this release."""
        return {app.app_id for app in self.applications}


# --------------------------------------------------------------------------
# Quality and delivery data
# --------------------------------------------------------------------------


class Defect(GovernanceModel):
    """A defect logged against an application in a release."""

    defect_id: str = Field(pattern=r"^DEF-\d+$")
    release_id: str = Field(pattern=RELEASE_ID_PATTERN)
    application_id: str = Field(pattern=APPLICATION_ID_PATTERN)
    title: str = Field(min_length=1, max_length=300)
    severity: Severity
    status: DefectStatus = DefectStatus.OPEN
    created_at: AwareDatetime
    resolved_at: AwareDatetime | None = None
    assignee: str | None = None
    # A blocking defect must be fixed before the release can ship.
    is_blocking: bool = False

    @model_validator(mode="after")
    def _check_dates(self) -> Self:
        """Ensure the resolution time is consistent with status and creation time."""
        _ensure_not_before(self.created_at, self.resolved_at, "created_at", "resolved_at")
        if self.status in {DefectStatus.RESOLVED, DefectStatus.CLOSED} and self.resolved_at is None:
            raise ValueError(f"resolved_at is required when status is {self.status}")
        return self

    @property
    def is_open(self) -> bool:
        """Whether the defect is still unresolved."""
        return self.status.is_open


class PipelineStage(GovernanceModel):
    """One stage (build, test, scan, deploy, ...) of a pipeline run."""

    name: str = Field(min_length=1)
    status: PipelineStatus
    duration_seconds: NonNegativeInt = 0


class Pipeline(GovernanceModel):
    """A CI/CD pipeline run that built or deployed an application."""

    pipeline_id: str = Field(min_length=1)
    release_id: str = Field(pattern=RELEASE_ID_PATTERN)
    application_id: str = Field(pattern=APPLICATION_ID_PATTERN)
    name: str = Field(min_length=1)
    status: PipelineStatus
    build_number: int = Field(ge=1)
    branch: str = "main"
    commit_sha: str | None = Field(default=None, pattern=COMMIT_SHA_PATTERN)
    started_at: AwareDatetime
    finished_at: AwareDatetime | None = None
    stages: list[PipelineStage] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_dates(self) -> Self:
        """Ensure a run finishes after it starts, and only running runs lack an end time."""
        _ensure_not_before(self.started_at, self.finished_at, "started_at", "finished_at")
        if self.status is not PipelineStatus.RUNNING and self.finished_at is None:
            raise ValueError(f"finished_at is required when status is {self.status}")
        return self


class RegressionResult(GovernanceModel):
    """Results of one regression test suite run for a release."""

    suite_id: str = Field(min_length=1)
    release_id: str = Field(pattern=RELEASE_ID_PATTERN)
    application_id: str = Field(pattern=APPLICATION_ID_PATTERN)
    suite_name: str = Field(min_length=1)
    total_tests: NonNegativeInt
    passed: NonNegativeInt
    failed: NonNegativeInt = 0
    skipped: NonNegativeInt = 0
    blocked: NonNegativeInt = 0
    # Share of the release's scope (requirements / changed code) this suite covers.
    coverage_percent: float = Field(ge=0, le=100)
    environment: Environment = Environment.QA
    executed_at: AwareDatetime

    @model_validator(mode="after")
    def _check_totals(self) -> Self:
        """Ensure the outcome counts add up to the total."""
        counted = self.passed + self.failed + self.skipped + self.blocked
        if counted != self.total_tests:
            raise ValueError(
                f"passed + failed + skipped + blocked ({counted}) "
                f"must equal total_tests ({self.total_tests})"
            )
        return self

    @property
    def pass_rate(self) -> float:
        """Percentage of all tests that passed (0 when the suite is empty)."""
        return 100.0 * self.passed / self.total_tests if self.total_tests else 0.0


class Approval(GovernanceModel):
    """A sign-off (or pending request for one) on a release."""

    approval_id: str = Field(min_length=1)
    release_id: str = Field(pattern=RELEASE_ID_PATTERN)
    role: ApprovalRole
    approver: str = Field(min_length=1)
    status: ApprovalStatus = ApprovalStatus.PENDING
    # Optional approvals are informational and don't count toward readiness.
    required: bool = True
    requested_at: AwareDatetime
    decided_at: AwareDatetime | None = None
    comments: str | None = None

    @model_validator(mode="after")
    def _check_decision(self) -> Self:
        """Ensure decided approvals have a decision time after the request."""
        if self.status is not ApprovalStatus.PENDING and self.decided_at is None:
            raise ValueError(f"decided_at is required when status is {self.status}")
        _ensure_not_before(self.requested_at, self.decided_at, "requested_at", "decided_at")
        return self


class FreezeWindow(GovernanceModel):
    """A period when production changes are restricted."""

    freeze_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    start: AwareDatetime
    end: AwareDatetime
    freeze_type: FreezeType = FreezeType.HARD
    # Empty means the freeze applies to every environment.
    environments: list[Environment] = Field(default_factory=lambda: [Environment.PRODUCTION])
    reason: str | None = None
    exception_contact: str | None = None

    @model_validator(mode="after")
    def _check_range(self) -> Self:
        """Ensure the window ends after it starts."""
        if self.end <= self.start:
            raise ValueError("end must be later than start")
        return self

    def covers(self, moment: datetime, environment: Environment) -> bool:
        """Whether this freeze applies to ``environment`` at ``moment``.

        Args:
            moment: A timezone-aware point in time.
            environment: The environment being changed.

        Returns:
            ``True`` if the moment falls inside the window (inclusive) and
            the environment is affected.
        """
        applies_to_environment = not self.environments or environment in self.environments
        return applies_to_environment and self.start <= moment <= self.end


class HistoricalRelease(GovernanceModel):
    """Outcome data for a past production release, used for trend analysis."""

    release_id: str = Field(pattern=RELEASE_ID_PATTERN)
    version: str = Field(pattern=VERSION_PATTERN)
    released_at: AwareDatetime
    outcome: ReleaseOutcome
    application_ids: list[str] = Field(default_factory=list)
    post_release_defects: NonNegativeInt = 0
    critical_post_release_defects: NonNegativeInt = 0
    rollback_performed: bool = False
    downtime_minutes: NonNegativeInt = 0
    deployment_duration_minutes: NonNegativeInt | None = None
    change_ticket: str | None = None

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        """Ensure defect counts and rollback flag agree with the outcome."""
        if self.critical_post_release_defects > self.post_release_defects:
            raise ValueError("critical_post_release_defects cannot exceed post_release_defects")
        if (self.outcome is ReleaseOutcome.ROLLED_BACK) != self.rollback_performed:
            raise ValueError("rollback_performed must be true exactly when outcome is ROLLED_BACK")
        return self


# --------------------------------------------------------------------------
# Configuration (config/rules.yaml and config/weights.yaml)
# --------------------------------------------------------------------------


class ReadinessRules(ConfigModel):
    """Thresholds a release must meet to be considered ready."""

    max_open_critical_defects: NonNegativeInt = 0
    max_open_high_defects: NonNegativeInt = 3
    min_regression_pass_rate: float = Field(default=95.0, ge=0, le=100)
    min_regression_coverage: float = Field(default=90.0, ge=0, le=100)
    required_pipeline_status: PipelineStatus = PipelineStatus.SUCCESS
    required_approval_roles: list[ApprovalRole] = Field(
        default_factory=lambda: [ApprovalRole.QA_LEAD, ApprovalRole.CHANGE_ADVISORY_BOARD]
    )
    block_during_freeze: bool = True


class HistoryRules(ConfigModel):
    """How historical releases are used in analysis."""

    lookback_releases: int = Field(default=12, ge=1)
    max_rollback_rate: float = Field(default=0.10, ge=0, le=1)


class GovernanceRuleConfig(ConfigModel):
    """One configurable governance rule used by Phase 2."""

    name: str = Field(min_length=1)
    field: str | None = None
    operator: str = "gt"
    value: str | int | float | bool | None = None
    description: str | None = None
    recommendation: str = ""
    outcome: str = "BLOCK"
    warning: bool = False
    mandatory: bool = True


class GovernanceRulesConfig(ConfigModel):
    """Container for governance rule definitions."""

    rules: list[GovernanceRuleConfig] = Field(default_factory=list)


class RulesConfig(ConfigModel):
    """Contents of ``config/rules.yaml``."""

    version: str = "1.0"
    readiness: ReadinessRules = Field(default_factory=ReadinessRules)
    history: HistoryRules = Field(default_factory=HistoryRules)
    governance: GovernanceRulesConfig | None = None
    rules: list[GovernanceRuleConfig] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_governance_rules(cls, values: object) -> object:
        """Support the legacy readiness format and the new governance rule list."""
        if not isinstance(values, dict):
            return values
        if "governance" not in values and "rules" in values and isinstance(values["rules"], list):
            values["governance"] = {"rules": values["rules"]}
        return values


class ScoringWeights(ConfigModel):
    """Relative importance of each signal in the future readiness score.

    Weights must add up to 1.0.
    """

    defects: float = Field(ge=0, le=1)
    testing: float = Field(ge=0, le=1)
    pipeline: float = Field(ge=0, le=1)
    approvals: float = Field(ge=0, le=1)
    freeze: float = Field(ge=0, le=1)
    history: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _check_sum(self) -> Self:
        """Ensure the weights add up to 1.0 (allowing for float rounding)."""
        total = sum(self.model_dump().values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"weights must add up to 1.0, got {total:.4f}")
        return self


class DecisionThresholds(ConfigModel):
    """Score cut-offs (0-100) for the future go / conditional-go / no-go decision."""

    go: float = Field(default=80.0, ge=0, le=100)
    conditional_go: float = Field(default=60.0, ge=0, le=100)

    @model_validator(mode="after")
    def _check_order(self) -> Self:
        """Ensure the go threshold is above the conditional-go threshold."""
        if self.go <= self.conditional_go:
            raise ValueError("go threshold must be greater than conditional_go")
        return self


class WeightsConfig(ConfigModel):
    """Contents of ``config/weights.yaml``."""

    version: str = "1.0"
    weights: ScoringWeights
    thresholds: DecisionThresholds = Field(default_factory=DecisionThresholds)
