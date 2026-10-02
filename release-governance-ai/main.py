"""Command-line entry point for the AI Release Governance Assistant (Phase 1).

Loads configuration and every dataset, validates them, and prints a summary
of the selected release. No AI reasoning happens in this phase.

Exit codes:
    0  Success.
    1  The requested release was not found.
    2  Configuration is missing or invalid.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from src.config_loader import AppConfig, ConfigLoader
from src.data_loader import ReleaseDataLoader
from src.exceptions import ConfigurationError, MissingFileError, ReleaseNotFoundError
from src.logger import get_logger, setup_logging
from src.summary import build_summary, format_summary
from src.validator import DataIntegrityValidator

PROJECT_ROOT = Path(__file__).resolve().parent
EXIT_OK = 0
EXIT_RELEASE_NOT_FOUND = 1
EXIT_CONFIG_ERROR = 2

logger = get_logger(__name__)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Arguments to parse; defaults to ``sys.argv[1:]``.

    Returns:
        The parsed arguments.
    """
    parser = argparse.ArgumentParser(description="AI Release Governance Assistant (Phase 1)")
    parser.add_argument(
        "--release-id",
        help="Release to summarize, e.g. REL-2026.10 (default: next active release)",
    )
    parser.add_argument(
        "--config-dir", type=Path, default=PROJECT_ROOT / "config",
        help="Folder with rules.yaml and weights.yaml",
    )
    parser.add_argument(
        "--data-dir", type=Path, default=PROJECT_ROOT / "data",
        help="Folder with the JSON datasets",
    )
    parser.add_argument(
        "--log-dir", type=Path, default=PROJECT_ROOT / "logs",
        help="Folder for log files",
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true",
        help="Only show warnings and errors on the console",
    )
    return parser.parse_args(argv)


def load_config(config_dir: Path) -> AppConfig | None:
    """Load configuration, logging and returning ``None`` on failure."""
    try:
        return ConfigLoader(config_dir).load()
    except (ConfigurationError, MissingFileError) as exc:
        logger.error("Cannot start: %s", exc)
        return None


def run(args: argparse.Namespace) -> int:
    """Load, validate, and summarize release data.

    Args:
        args: Parsed command-line arguments.

    Returns:
        The process exit code.
    """
    if load_config(args.config_dir) is None:
        return EXIT_CONFIG_ERROR

    dataset = ReleaseDataLoader(args.data_dir).load_all()
    integrity_issues = DataIntegrityValidator().validate(dataset)

    try:
        snapshot = dataset.snapshot(args.release_id)
    except ReleaseNotFoundError as exc:
        logger.error("%s", exc)
        return EXIT_RELEASE_NOT_FOUND

    summary = build_summary(snapshot, data_issues=len(dataset.issues) + len(integrity_issues))
    logger.info("Summary built for %s", summary.release_id)
    print(format_summary(summary))
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    """Program entry point.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        The process exit code.
    """
    args = parse_args(argv)
    log_file = setup_logging(args.log_dir, console_level=logging.WARNING if args.quiet else logging.INFO)
    logger.info("Starting AI Release Governance Assistant (log file: %s)", log_file)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
