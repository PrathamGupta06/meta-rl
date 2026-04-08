"""Client for the K8s architecture generation environment."""

from typing import Dict

from openenv.core import EnvClient
from openenv.core.client_types import StepResult

try:
    from .models import (
        KubeArchitectGymAction,
        KubeArchitectGymObservation,
        KubeArchitectGymState,
    )
except ImportError:
    from models import (
        KubeArchitectGymAction,
        KubeArchitectGymObservation,
        KubeArchitectGymState,
    )


class KubeArchitectGymEnv(
    EnvClient[KubeArchitectGymAction, KubeArchitectGymObservation, KubeArchitectGymState]
):
    """Typed OpenEnv client for local use and baseline inference."""

    def __init__(self, base_url: str, **kwargs):
        kwargs.setdefault("message_timeout_s", 120.0)
        super().__init__(base_url=base_url, **kwargs)

    def _step_payload(self, action: KubeArchitectGymAction) -> Dict:
        return {"manifest_yaml": action.manifest_yaml, "finalize": action.finalize}

    def _parse_result(self, payload: Dict) -> StepResult[KubeArchitectGymObservation]:
        obs_data = payload.get("observation", {})
        observation = KubeArchitectGymObservation(
            task_id=obs_data.get("task_id", ""),
            task_name=obs_data.get("task_name", ""),
            task_brief=obs_data.get("task_brief", ""),
            previous_feedback=obs_data.get("previous_feedback", ""),
            llm_feedback=obs_data.get("llm_feedback", ""),
            score_breakdown=obs_data.get("score_breakdown", {}),
            validation_issues=obs_data.get("validation_issues", []),
            resource_summary=obs_data.get("resource_summary", []),
            steps_taken=obs_data.get("steps_taken", 0),
            max_steps=obs_data.get("max_steps", 6),
            is_valid_yaml=obs_data.get("is_valid_yaml", False),
            done=payload.get("done", False),
            reward=payload.get("reward"),
            metadata=obs_data.get("metadata", {}),
        )
        return StepResult(
            observation=observation,
            reward=payload.get("reward"),
            done=payload.get("done", False),
        )

    def _parse_state(self, payload: Dict) -> KubeArchitectGymState:
        return KubeArchitectGymState(
            episode_id=payload.get("episode_id"),
            step_count=payload.get("step_count", 0),
            task_id=payload.get("task_id", ""),
            task_name=payload.get("task_name", ""),
            latest_manifest_yaml=payload.get("latest_manifest_yaml", ""),
            parsed_resource_summary=payload.get("parsed_resource_summary", []),
            violations=payload.get("violations", []),
            score_breakdown=payload.get("score_breakdown", {}),
            llm_feedback=payload.get("llm_feedback", ""),
            current_score=payload.get("current_score", 0.0),
            is_resolved=payload.get("is_resolved", False),
        )
