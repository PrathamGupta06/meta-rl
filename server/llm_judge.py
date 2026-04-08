"""Optional LLM judge used only for dense reward shaping and coaching."""

from __future__ import annotations

import json
import os

from openai import OpenAI

try:
    from ..models import GradeResult, JudgeResult, TaskSpec
except ImportError:
    from models import GradeResult, JudgeResult, TaskSpec


SYSTEM_PROMPT = """You are a strict cloud platform architect reviewing Kubernetes manifests.
Return JSON only with:
{
  "architecture_quality_score": -1.0 to 1.0,
  "reasoning_quality_score": -1.0 to 1.0,
  "feedback": "short feedback",
  "next_best_fix": "single highest-leverage improvement"
}
Base your response on topology correctness, security hardening, and cost awareness.
Do not reward patterns already flagged as invalid by the deterministic grader.
"""


class LLMJudge:
    """Small wrapper around an OpenAI-compatible endpoint."""

    def __init__(self):
        base_url = os.getenv("LLM_JUDGE_BASE_URL") or os.getenv("API_BASE_URL")
        model = os.getenv("LLM_JUDGE_MODEL") or os.getenv("MODEL_NAME")
        api_key = (
            os.getenv("LLM_JUDGE_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("HF_TOKEN")
        )
        self.enabled = bool(base_url and model and api_key)
        self.model = model
        self._client = OpenAI(base_url=base_url, api_key=api_key) if self.enabled else None

    def evaluate(
        self,
        task: TaskSpec,
        manifest_yaml: str,
        grade_result: GradeResult,
        previous_feedback: str,
    ) -> JudgeResult:
        """Return bounded shaping feedback. Falls back to neutral on any error."""

        if not self.enabled or self._client is None:
            return JudgeResult()

        user_prompt = (
            f"Task:\n{task.brief}\n\n"
            f"Deterministic score: {grade_result.total_score:.3f}\n"
            f"Deterministic feedback: {grade_result.feedback}\n"
            f"Previous grader feedback: {previous_feedback or 'none'}\n\n"
            f"Manifest submission:\n```yaml\n{manifest_yaml[:12000]}\n```"
        )
        try:
            completion = self._client.chat.completions.create(
                model=self.model,
                temperature=0.1,
                max_tokens=300,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )
            text = (completion.choices[0].message.content or "").strip()
            payload = json.loads(text)
            arch = float(payload.get("architecture_quality_score", 0.0))
            reasoning = float(payload.get("reasoning_quality_score", 0.0))
            shaping = max(-0.15, min(0.15, (arch + reasoning) / 20.0))
            return JudgeResult(
                shaping_bonus=shaping,
                feedback=str(payload.get("feedback", "")),
                next_best_fix=str(payload.get("next_best_fix", "")),
                raw_score=max(-1.0, min(1.0, (arch + reasoning) / 2.0)),
            )
        except Exception as exc:
            return JudgeResult(feedback=f"LLM judge unavailable: {exc}")
