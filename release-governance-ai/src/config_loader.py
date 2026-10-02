"""Loading and validation of YAML configuration files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from src.exceptions import ConfigurationError, MissingFileError
from src.logger import get_logger
from src.models import RulesConfig, WeightsConfig, format_validation_errors

logger = get_logger(__name__)

RULES_FILE = "rules.yaml"
WEIGHTS_FILE = "weights.yaml"


@dataclass(frozen=True)
class AppConfig:
    """All application configuration, validated and strongly typed."""

    rules: RulesConfig
    weights: WeightsConfig


class ConfigLoader:
    """Loads YAML configuration files from a directory into typed models."""

    def __init__(self, config_dir: Path) -> None:
        """Create a loader for ``config_dir``.

        Args:
            config_dir: Directory containing ``rules.yaml`` and ``weights.yaml``.
        """
        self.config_dir = config_dir

    def load(self) -> AppConfig:
        """Load every configuration file.

        Returns:
            The complete, validated configuration.

        Raises:
            MissingFileError: A configuration file does not exist.
            ConfigurationError: A file is malformed or fails validation.
        """
        config = AppConfig(rules=self.load_rules(), weights=self.load_weights())
        logger.info("Configuration loaded from %s", self.config_dir)
        return config

    def load_rules(self) -> RulesConfig:
        """Load ``rules.yaml``.

        Raises:
            MissingFileError: The file does not exist.
            ConfigurationError: The file is malformed or fails validation.
        """
        return self._load_model(self.config_dir / RULES_FILE, RulesConfig)

    def load_weights(self) -> WeightsConfig:
        """Load ``weights.yaml``.

        Raises:
            MissingFileError: The file does not exist.
            ConfigurationError: The file is malformed or fails validation.
        """
        return self._load_model(self.config_dir / WEIGHTS_FILE, WeightsConfig)

    def _load_model[M: BaseModel](self, path: Path, model: type[M]) -> M:
        """Read ``path`` and validate it against ``model``."""
        data = load_yaml_mapping(path)
        try:
            parsed = model.model_validate(data)
        except ValidationError as exc:
            details = "; ".join(format_validation_errors(exc))
            raise ConfigurationError(f"Invalid configuration in {path}: {details}") from exc
        logger.debug("Loaded %s as %s", path.name, model.__name__)
        return parsed


def load_yaml_mapping(path: Path) -> dict[str, Any]:
    """Read a YAML file whose top level must be a mapping.

    Args:
        path: The YAML file to read.

    Returns:
        The parsed mapping.

    Raises:
        MissingFileError: The file does not exist.
        ConfigurationError: The file can't be read, isn't valid YAML, or
            its top level isn't a mapping.
    """
    if not path.is_file():
        raise MissingFileError(path, "Configuration file")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"Invalid YAML in {path}: {exc}") from exc
    except OSError as exc:
        raise ConfigurationError(f"Cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigurationError(f"{path} must contain a YAML mapping at the top level")
    return data
