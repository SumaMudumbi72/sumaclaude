"""Deterministic evaluation engine for release governance rules."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from src.rule_models import OverallDecision, RuleDefinition, RuleStatus
from src.rule_result import RuleEvaluation, RuleResult


class RuleLoader:
    """Load YAML governance rules into typed rule definitions."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> list[RuleDefinition]:
        """Read and normalize governance rules from the YAML configuration."""
        if not self.path.is_file():
            raise FileNotFoundError(f"Rule file not found: {self.path}")

        payload = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise ValueError(f"Rule file must contain a YAML mapping: {self.path}")

        rule_list = self._extract_rules(payload)
        if not rule_list:
            return []
        return [self._normalize_rule(rule) for rule in rule_list]

    @staticmethod
    def _extract_rules(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        """Find the governance rules section across supported YAML layouts."""
        candidates = []
        for key in ("governance", "rules"):
            value = payload.get(key)
            if isinstance(value, list):
                candidates = value
                break
            if isinstance(value, dict):
                nested = value.get("rules")
                if isinstance(nested, list):
                    candidates = nested
                    break
        if not candidates:
            return []
        return [rule for rule in candidates if isinstance(rule, Mapping)]

    @staticmethod
    def _normalize_rule(raw_rule: Mapping[str, Any]) -> RuleDefinition:
        """Convert a YAML mapping into a RuleDefinition."""
        name = str(raw_rule.get("name") or raw_rule.get("rule_name") or raw_rule.get("title") or "Unnamed Rule")
        field = raw_rule.get("field") or raw_rule.get("metric") or raw_rule.get("attribute")
        comparison = str(raw_rule.get("operator") or raw_rule.get("comparison") or "gt")
        threshold = raw_rule.get("value")
        if threshold is None:
            threshold = raw_rule.get("threshold")
        recommendation = str(raw_rule.get("recommendation") or raw_rule.get("action") or raw_rule.get("fix") or "")
        outcome = str(raw_rule.get("outcome") or raw_rule.get("kind") or raw_rule.get("decision") or "BLOCK")
        if outcome.lower() == "conditional":
            outcome = OverallDecision.CONDITIONAL_APPROVAL.value
        if outcome.lower() == "block":
            outcome = OverallDecision.BLOCK.value
        if outcome.lower() == "escalate":
            outcome = OverallDecision.ESCALATE.value
        warning_flag = bool(raw_rule.get("warning") or raw_rule.get("warning_only") or outcome == OverallDecision.CONDITIONAL_APPROVAL.value)
        mandatory = bool(raw_rule.get("mandatory", True))
        return RuleDefinition(
            name=name,
            field=str(field) if field is not None else None,
            operator=comparison,
            value=threshold,
            description=str(raw_rule.get("description") or ""),
            recommendation=recommendation,
            outcome=outcome,
            warning=warning_flag,
            mandatory=mandatory,
        )


class RuleEvaluator:
    """Evaluate rule definitions against a dictionary of release metrics."""

    def __init__(self, rules: Sequence[RuleDefinition] | None = None) -> None:
        self.rules = list(rules or [])

    def evaluate(self, metrics: Mapping[str, Any]) -> RuleEvaluation:
        """Evaluate all configured rules for the supplied metrics."""
        rule_results = [self.evaluate_rule(rule, metrics) for rule in self.rules]
        overall = self._overall_recommendation(rule_results)
        reasons = [r.evidence for r in rule_results if r.status != RuleStatus.PASS.value]
        next_actions = [r.recommendation for r in rule_results if r.status != RuleStatus.PASS.value and r.recommendation]
        return RuleEvaluation(
            rule_name="",
            status="",
            evidence="",
            recommendation="",
            outcome="",
            rule_results=rule_results,
            overall_recommendation=overall,
            reasons=reasons,
            next_actions=next_actions,
        )

    def evaluate_rule(self, rule: RuleDefinition, metrics: Mapping[str, Any]) -> RuleResult:
        """Evaluate a single rule and return the structured result."""
        actual_value = metrics.get(rule.field) if rule.field is not None else None
        triggered = self._matches(actual_value, rule.operator, rule.value)
        passed = not triggered

        if passed:
            status = RuleStatus.PASS.value
            evidence = self._build_evidence(rule, actual_value, rule.value, "is within threshold")
            recommendation = ""
            outcome = rule.outcome
        else:
            status = RuleStatus.WARNING.value if rule.warning else RuleStatus.FAIL.value
            evidence = self._build_evidence(rule, actual_value, rule.value, "triggered")
            recommendation = rule.recommendation or self._default_recommendation(rule)
            outcome = rule.outcome

        return RuleResult(
            rule_name=rule.name,
            status=status,
            evidence=evidence,
            recommendation=recommendation,
            outcome=outcome,
        )

    @staticmethod
    def _matches(actual: Any, operator: str, expected: Any) -> bool:
        """Compare a metric to a configured threshold."""
        op = (operator or "eq").lower()
        if op == "eq":
            return actual == expected
        if op == "ne":
            return actual != expected
        if op == "gt":
            return bool(actual is not None and actual > expected)
        if op == "gte":
            return bool(actual is not None and actual >= expected)
        if op == "lt":
            return bool(actual is not None and actual < expected)
        if op == "lte":
            return bool(actual is not None and actual <= expected)
        if op in {"is_true", "true"}:
            return bool(actual is True)
        if op in {"is_false", "false"}:
            return bool(actual is False)
        if op == "in":
            return actual in expected if isinstance(expected, Iterable) and not isinstance(expected, (str, bytes)) else False
        if op == "contains":
            return bool(expected is not None and str(expected) in str(actual)) if actual is not None else False
        return actual == expected

    @staticmethod
    def _build_evidence(rule: RuleDefinition, actual: Any, expected: Any, verb: str) -> str:
        """Build a human-readable explanation for the rule result."""
        field = rule.field or rule.name
        if actual is None:
            return f"{rule.name}: no metric available for {field}"
        if isinstance(actual, bool):
            actual_label = "true" if actual else "false"
            threshold_label = "true" if expected else "false"
            return f"{rule.name}: {actual_label} {verb} {threshold_label}"
        if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
            return f"{rule.name}: {actual} {verb} {expected}"
        return f"{rule.name}: {actual} {verb} {expected}"

    @staticmethod
    def _default_recommendation(rule: RuleDefinition) -> str:
        """Generate a default fix recommendation when the YAML rule omits one."""
        if rule.recommendation:
            return rule.recommendation
        return f"Review {rule.name}"

    @staticmethod
    def _overall_recommendation(results: Sequence[RuleResult]) -> str:
        """Compute the aggregated release recommendation."""
        if any(result.status == RuleStatus.FAIL.value and result.outcome == OverallDecision.BLOCK.value for result in results):
            return OverallDecision.BLOCK.value
        if any(result.status == RuleStatus.FAIL.value and result.outcome == OverallDecision.ESCALATE.value for result in results):
            return OverallDecision.ESCALATE.value
        if any(result.status == RuleStatus.WARNING.value for result in results):
            return OverallDecision.CONDITIONAL_APPROVAL.value
        return OverallDecision.PROCEED.value


class RuleEngine:
    """Convenience wrapper for loading and evaluating rules from YAML."""

    def __init__(self, config_path: str | Path | None = None, rules: Sequence[RuleDefinition] | None = None) -> None:
        self.config_path = Path(config_path) if config_path is not None else None
        self.rules = list(rules or [])
        if self.config_path is not None:
            self.rules = RuleLoader(self.config_path).load() if not self.rules else list(self.rules)
        self.evaluator = RuleEvaluator(self.rules)

    def evaluate(self, metrics: Mapping[str, Any]) -> RuleEvaluation:
        """Evaluate the configured rules for the given metrics."""
        return self.evaluator.evaluate(metrics)


def evaluate_rules(metrics: Mapping[str, Any], config_path: str | Path | None = None, rules: Sequence[RuleDefinition] | None = None) -> RuleEvaluation:
    """Utility helper: evaluate a metric map using YAML-configured rules."""
    engine = RuleEngine(config_path=config_path, rules=rules)
    return engine.evaluate(metrics)


__all__ = [
    "RuleEngine",
    "RuleEvaluator",
    "RuleLoader",
    "evaluate_rules",
]
