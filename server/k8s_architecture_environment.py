"""OpenEnv environment for Kubernetes architecture generation."""

from __future__ import annotations

import os
from uuid import uuid4

from openenv.core.env_server.interfaces import Environment

try:
    from ..models import (
        GradeResult,
        KubeArchitectGymAction,
        KubeArchitectGymObservation,
        KubeArchitectGymState,
    )
    from .deterministic_grader import grade_submission
    from .llm_judge import LLMJudge
    from .reward_mixer import compute_step_reward
    from .task_registry import TASKS, get_task
except ImportError:
    from models import (
        GradeResult,
        KubeArchitectGymAction,
        KubeArchitectGymObservation,
        KubeArchitectGymState,
    )
    from server.deterministic_grader import grade_submission
    from server.llm_judge import LLMJudge
    from server.reward_mixer import compute_step_reward
    from server.task_registry import TASKS, get_task


class K8sArchitectureEnvironment(Environment):
    """Iterative environment for architecture manifest generation."""

    SUPPORTS_CONCURRENT_SESSIONS: bool = False
    _INITIAL_SCORE = 0.01

    def __init__(self):
        self.task_sequence = list(TASKS)
        self.default_max_steps = int(os.getenv("MAX_STEPS", "7"))
        self.default_task_id = os.getenv("DEFAULT_TASK_ID", "")
        self.judge = LLMJudge()
        self._task_cursor = 0
        self._history: list[str] = []
        self._grade_history: list[GradeResult] = []
        self._steps_taken = 0
        self._task = self.task_sequence[0]
        self._state = KubeArchitectGymState(episode_id=str(uuid4()), step_count=0)

    def reset(self, seed=None, episode_id=None, **kwargs) -> KubeArchitectGymObservation:
        """Reset to the next benchmark task or a configured task id."""

        requested_task_id = kwargs.get("task_id") or self.default_task_id
        if requested_task_id:
            self._task = get_task(requested_task_id)
        else:
            self._task = self.task_sequence[self._task_cursor % len(self.task_sequence)]
            self._task_cursor += 1

        self._steps_taken = 0
        self._history = []
        self._grade_history = []
        self._state = KubeArchitectGymState(
            episode_id=episode_id or str(uuid4()),
            step_count=0,
            task_id=self._task.task_id,
            task_name=self._task.task_name,
            latest_manifest_yaml="",
            parsed_resource_summary=[],
            violations=[],
            score_breakdown={
                "validity": self._INITIAL_SCORE,
                "topology": self._INITIAL_SCORE,
                "security": self._INITIAL_SCORE,
                "cost": self._INITIAL_SCORE,
            },
            llm_feedback="",
            current_score=self._INITIAL_SCORE,
            is_resolved=False,
        )
        return self._build_observation(
            feedback="Submit a multi-document Kubernetes manifest that satisfies the task constraints.",
            llm_feedback="",
            is_valid_yaml=False,
            reward=self._INITIAL_SCORE,
            done=False,
        )

    def step(self, action: KubeArchitectGymAction, timeout_s=None, **kwargs) -> KubeArchitectGymObservation:
        """Grade the submitted manifest and return dense feedback."""

        self._steps_taken += 1
        repeated_submission = bool(self._history and action.manifest_yaml.strip() == self._history[-1].strip())
        previous_grade = self._grade_history[-1] if self._grade_history else None
        current_grade = grade_submission(self._task, action.manifest_yaml)
        judge_result = self.judge.evaluate(
            self._task,
            action.manifest_yaml,
            current_grade,
            previous_grade.feedback if previous_grade else "",
        )
        reward = compute_step_reward(
            self._task,
            previous_grade,
            current_grade,
            judge_result,
            action.finalize,
            repeated_submission,
        )
        done = False
        if action.finalize and current_grade.total_score >= self._task.success_threshold:
            done = True
        if self._steps_taken >= min(self.default_max_steps, self._task.max_steps):
            done = True

        llm_feedback = judge_result.feedback
        feedback = current_grade.feedback
        if judge_result.next_best_fix:
            llm_feedback = f"{judge_result.feedback} Next best fix: {judge_result.next_best_fix}".strip()

        self._history.append(action.manifest_yaml)
        self._grade_history.append(current_grade)
        self._state.step_count = self._steps_taken
        self._state.task_id = self._task.task_id
        self._state.task_name = self._task.task_name
        self._state.latest_manifest_yaml = action.manifest_yaml
        self._state.parsed_resource_summary = current_grade.resource_summary
        self._state.violations = [issue.message for issue in current_grade.issues]
        self._state.score_breakdown = current_grade.score_breakdown
        self._state.llm_feedback = llm_feedback
        self._state.current_score = current_grade.total_score
        self._state.is_resolved = done and current_grade.total_score >= self._task.success_threshold

        if done and not self._state.is_resolved:
            feedback = f"{feedback} Episode ended before reaching the success threshold."

        return self._build_observation(
            feedback=feedback,
            llm_feedback=llm_feedback,
            is_valid_yaml=current_grade.valid,
            reward=reward,
            done=done,
            grade=current_grade,
        )

    @property
    def state(self) -> KubeArchitectGymState:
        return self._state

    def _build_observation(
        self,
        feedback: str,
        llm_feedback: str,
        is_valid_yaml: bool,
        reward: float,
        done: bool,
        grade: GradeResult | None = None,
    ) -> KubeArchitectGymObservation:
        grade = grade or GradeResult(
            valid=False,
            score_breakdown=self._state.score_breakdown or {
                "validity": self._INITIAL_SCORE,
                "topology": self._INITIAL_SCORE,
                "security": self._INITIAL_SCORE,
                "cost": self._INITIAL_SCORE,
            },
            total_score=self._state.current_score,
            issues=[],
            resource_summary=[],
            feedback=feedback,
        )
        return KubeArchitectGymObservation(
            task_id=self._task.task_id,
            task_name=self._task.task_name,
            task_brief=self._task.brief,
            previous_feedback=feedback,
            llm_feedback=llm_feedback,
            score_breakdown={**grade.score_breakdown, "total": grade.total_score},
            validation_issues=[issue.message for issue in grade.issues],
            resource_summary=grade.resource_summary,
            steps_taken=self._steps_taken,
            max_steps=min(self.default_max_steps, self._task.max_steps),
            is_valid_yaml=is_valid_yaml,
            done=done,
            reward=reward,
        )
