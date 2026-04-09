"""Reward shaping helpers for iterative manifest refinement."""

from __future__ import annotations

try:
    from ..models import GradeResult, JudgeResult, TaskSpec
except ImportError:
    from models import GradeResult, JudgeResult, TaskSpec


STRICT_MIN = 0.01
STRICT_MAX = 0.99


def _strict_unit_interval(value: float) -> float:
    """Clamp reward into the strict open interval (0, 1)."""

    return round(max(STRICT_MIN, min(STRICT_MAX, value)), 4)


def compute_step_reward(
    task: TaskSpec,
    previous_grade: GradeResult | None,
    current_grade: GradeResult,
    judge_result: JudgeResult,
    finalize: bool,
    repeated_submission: bool,
) -> float:
    """Compute a bounded reward from quality, progress, and small judge shaping."""

    previous_total = previous_grade.total_score if previous_grade else STRICT_MIN
    previous_topology = previous_grade.score_breakdown["topology"] if previous_grade else STRICT_MIN
    previous_security = previous_grade.score_breakdown["security"] if previous_grade else STRICT_MIN
    previous_validity = previous_grade.score_breakdown["validity"] if previous_grade else STRICT_MIN

    delta = current_grade.total_score - previous_total
    progress_signal = _strict_unit_interval(0.5 + delta)
    topology_gain = max(0.0, current_grade.score_breakdown["topology"] - previous_topology)
    security_gain = max(0.0, current_grade.score_breakdown["security"] - previous_security)
    validity_gain = max(0.0, current_grade.score_breakdown["validity"] - previous_validity)
    judge_signal = _strict_unit_interval(0.5 + (judge_result.raw_score * 0.5))

    reward = (
        0.55 * current_grade.total_score
        + 0.20 * progress_signal
        + 0.10 * judge_signal
        + 0.10 * topology_gain
        + 0.05 * (security_gain + validity_gain)
    )

    if repeated_submission and delta <= 0.01:
        reward *= 0.7

    if finalize:
        if current_grade.total_score >= task.success_threshold:
            reward = (0.8 * reward) + 0.18
        else:
            reward *= 0.85

    if not current_grade.valid:
        reward *= 0.4

    return _strict_unit_interval(reward)
