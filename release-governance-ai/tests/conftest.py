"""Pytest fixtures shared across the test suite."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests.helpers import SAMPLE_CONFIG_DIR, write_minimal_data_dir


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """Provide a writable copy of the sample configuration directory."""
    target = tmp_path / "config"
    shutil.copytree(SAMPLE_CONFIG_DIR, target)
    return target


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """Provide a small, valid data directory."""
    return write_minimal_data_dir(tmp_path / "data")
