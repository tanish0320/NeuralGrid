from __future__ import annotations

from typing import Any, Callable

from agents.twinnode.tasks.counterfactual_batch import run_counterfactual_batch
from agents.twinnode.tasks.scenario_evaluation import run_scenario_evaluation
from agents.twinnode.tasks.traffic_batch import run_traffic_batch
from apps.api.app.core.security import ALLOWED_TASK_TYPES, compute_canonical_checksum

TaskExecutor = Callable[[int, dict[str, Any]], dict[str, Any]]

ALLOWED_TASK_EXECUTORS: dict[str, TaskExecutor] = {
    "traffic_batch": run_traffic_batch,
    "scenario_evaluation": run_scenario_evaluation,
    "counterfactual_batch": run_counterfactual_batch,
}


class DisallowedTaskError(ValueError):
    """Raised when an unapproved or arbitrary task type is requested."""


def execute_allowlisted_task(
    task_type: str, seed: int, payload: dict[str, Any]
) -> tuple[dict[str, Any], str]:
    """Execute strictly allowlisted deterministic compute tasks; no arbitrary code/shell execution."""
    if task_type not in ALLOWED_TASK_TYPES or task_type not in ALLOWED_TASK_EXECUTORS:
        raise DisallowedTaskError(
            f"Task type '{task_type}' is not in allowlist {sorted(ALLOWED_TASK_TYPES)}"
        )
    executor = ALLOWED_TASK_EXECUTORS[task_type]
    result = executor(seed, payload)
    checksum = compute_canonical_checksum(result)
    return result, checksum
