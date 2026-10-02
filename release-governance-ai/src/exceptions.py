"""Custom exception hierarchy for the Release Governance Assistant.

Every exception raised deliberately by this application derives from
:class:`ReleaseGovernanceError`, so callers can catch application errors
without also swallowing unrelated programming errors.
"""

from __future__ import annotations

from pathlib import Path


class ReleaseGovernanceError(Exception):
    """Base class for all application-specific errors."""


class ConfigurationError(ReleaseGovernanceError):
    """A configuration file is unreadable, malformed, or fails validation."""


class MissingFileError(ReleaseGovernanceError):
    """A required file or directory does not exist."""

    def __init__(self, path: Path, description: str = "File") -> None:
        """Create the error for the missing ``path``.

        Args:
            path: The path that was expected to exist.
            description: What kind of path it is, used in the message.
        """
        self.path = path
        super().__init__(f"{description} not found: {path}")


class InvalidJsonError(ReleaseGovernanceError):
    """A file exists but does not contain valid JSON."""

    def __init__(self, path: Path, detail: str) -> None:
        """Create the error for the malformed file at ``path``.

        Args:
            path: The file that failed to parse.
            detail: The parser's explanation, including line and column.
        """
        self.path = path
        self.detail = detail
        super().__init__(f"Invalid JSON in {path}: {detail}")


class DataValidationError(ReleaseGovernanceError):
    """A record does not match its expected schema."""

    def __init__(self, source: str, errors: list[str]) -> None:
        """Create the error for the record identified by ``source``.

        Args:
            source: Human-readable location of the record, e.g. ``file.json[3]``.
            errors: One message per failed validation rule.
        """
        self.source = source
        self.errors = errors
        super().__init__(f"Validation failed for {source}: {'; '.join(errors)}")


class ReleaseNotFoundError(ReleaseGovernanceError):
    """The requested release does not exist in the loaded data."""

    def __init__(self, release_id: str | None) -> None:
        """Create the error for ``release_id``.

        Args:
            release_id: The ID that was looked up, or ``None`` when no
                release could be selected at all.
        """
        self.release_id = release_id
        message = (
            f"Release not found: {release_id}"
            if release_id
            else "No releases were found in the data directory"
        )
        super().__init__(message)
