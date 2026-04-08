"""Reward shaping helpers for iterative manifest refinement."""

from __future__ import annotations

try:
    from ..models import GradeResult, JudgeResult, TaskSpec
except ImportError:
    from models import GradeResult, JudgeResult, TaskSpec


def compute_step_reward(
    task: TaskSpec,
    previous_grade: GradeResult | None,
    current_grade: GradeResult,
    judge_result: JudgeResult,
    finalize: bool,
    repeated_submission: bool,
) -> float:
    """Blend score improvement with optional LLM shaping."""

    previous_total = previous_grade.total_score if previous_grade else 0.0
    delta = current_grade.total_score - previous_total
    reward = delta * 2.2
    if previous_grade is None and current_grade.valid:
        reward += 0.1
    if current_grade.score_breakdown["topology"] > (previous_grade.score_breakdown["topology"] if previous_grade else 0.0):
        reward += 0.1
    if current_grade.score_breakdown["security"] > (previous_grade.score_breakdown["security"] if previous_grade else 0.0):
        reward += 0.08
    if repeated_submission and delta <= 0.01:
        reward -= 0.15
    if finalize:
        if current_grade.total_score >= task.success_threshold:
            reward += 0.75
        else:
            reward -= 0.2
    reward += judge_result.shaping_bonus
    return round(max(-1.0, min(1.5, reward)), 4)
