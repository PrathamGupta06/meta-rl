"""Baseline inference script for the Kube Architect Gym benchmark."""

from __future__ import annotations

import json
import os
import re
import sys

from openai import OpenAI

from client import KubeArchitectGymEnv
from models import KubeArchitectGymAction
from server.task_registry import TASKS

IMAGE_NAME = os.getenv("LOCAL_IMAGE_NAME") or os.getenv("IMAGE_NAME")
API_BASE_URL = os.getenv("API_BASE_URL") or "https://router.huggingface.co/v1"
MODEL_NAME = os.getenv("MODEL_NAME") or "Qwen/Qwen2.5-72B-Instruct"
API_KEY = os.getenv("HF_TOKEN") or os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY", "")
ENV_BASE_URL = os.getenv("ENV_BASE_URL", "http://127.0.0.1:8000")
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.2"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "2200"))
MAX_REFINEMENT_STEPS = int(os.getenv("MAX_REFINEMENT_STEPS", "3"))
BENCHMARK = os.getenv("KUBE_ARCHITECT_GYM_BENCHMARK", "kube_architect_gym")
SUCCESS_SCORE_THRESHOLD = float(os.getenv("SUCCESS_SCORE_THRESHOLD", "0.85"))

SYSTEM_PROMPT = """You are a senior platform engineer.
Generate only valid multi-document Kubernetes YAML that satisfies the task brief and feedback.
Use explicit image tags, resource requests and limits, probes, secure securityContext, and cost-aware sizing.
Do not include markdown explanations unless the user asks for them.
"""


def log_start(task: str, env: str, model: str) -> None:
    print(f"[START] task={task} env={env} model={model}", flush=True)


def log_step(step: int, action: str, reward: float, done: bool, error: str | None) -> None:
    safe_action = action.replace("\n", "\\n")
    safe_error = "null" if error is None else error.replace("\n", "\\n")
    print(
        f"[STEP] step={step} action={safe_action} reward={reward:.2f} done={str(done).lower()} error={safe_error}",
        flush=True,
    )


def log_end(success: bool, steps: int, score: float, rewards: list[float]) -> None:
    rewards_str = ",".join(f"{reward:.2f}" for reward in rewards)
    print(
        f"[END] success={str(success).lower()} steps={steps} score={score:.3f} rewards={rewards_str}",
        flush=True,
    )


def extract_manifest(text: str) -> str:
    """Extract YAML from fenced output when present."""

    match = re.search(r"```yaml\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text.strip()


def build_user_prompt(task_brief: str, last_feedback: str, score_breakdown: dict[str, float], history: list[str]) -> str:
    history_text = "\n".join(history[-3:]) if history else "No previous submissions."
    return (
        f"Task brief:\n{task_brief}\n\n"
        f"Latest deterministic feedback:\n{last_feedback or 'None yet.'}\n\n"
        f"Current score breakdown:\n{json.dumps(score_breakdown, indent=2, sort_keys=True)}\n\n"
        f"Previous attempts:\n{history_text}\n\n"
        "Return only the improved Kubernetes manifest YAML."
    )


def get_model_manifest(client: OpenAI, task_brief: str, last_feedback: str, score_breakdown: dict[str, float], history: list[str]) -> str:
    user_prompt = build_user_prompt(task_brief, last_feedback, score_breakdown, history)
    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            stream=False,
        )
        text = (completion.choices[0].message.content or "").strip()
        return extract_manifest(text)
    except Exception as exc:
        fallback = (
            "apiVersion: v1\nkind: Namespace\nmetadata:\n  name: fallback\n"
            f"# model_error: {exc}"
        )
        return fallback


def run_task(env: KubeArchitectGymEnv, client: OpenAI, index: int) -> float:
    """Run one benchmark task. Tasks are emitted by the server in fixed order."""

    task_spec = TASKS[index]
    rewards: list[float] = []
    history: list[str] = []
    steps_taken = 0

    log_start(task=task_spec.task_id, env=BENCHMARK, model=MODEL_NAME)
    result = env.reset()
    last_feedback = result.observation.previous_feedback
    score_breakdown = result.observation.score_breakdown

    for step in range(1, min(MAX_REFINEMENT_STEPS, result.observation.max_steps) + 1):
        manifest_yaml = get_model_manifest(
            client,
            result.observation.task_brief,
            last_feedback,
            score_breakdown,
            history,
        )
        finalize = step == min(MAX_REFINEMENT_STEPS, result.observation.max_steps)
        result = env.step(KubeArchitectGymAction(manifest_yaml=manifest_yaml, finalize=finalize))
        reward = float(result.reward or 0.0)
        rewards.append(reward)
        steps_taken = step
        last_feedback = result.observation.previous_feedback
        score_breakdown = result.observation.score_breakdown
        history.append(f"step={step} total={score_breakdown.get('total', 0.0):.4f}")
        error = None if result.observation.is_valid_yaml else "invalid_manifest"
        log_step(step=step, action=manifest_yaml, reward=reward, done=result.done, error=error)
        if result.done:
            break

    score = float(score_breakdown.get("total", 0.0))
    success = score >= max(task_spec.success_threshold, SUCCESS_SCORE_THRESHOLD)
    log_end(success=success, steps=steps_taken, score=score, rewards=rewards)
    return score


def main() -> None:
    if not API_KEY:
        raise RuntimeError("Set HF_TOKEN or OPENAI_API_KEY before running inference.py.")

    client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)
    scores: list[float] = []
    if IMAGE_NAME:
        env = KubeArchitectGymEnv.from_docker_image(IMAGE_NAME)
    else:
        env = KubeArchitectGymEnv(base_url=ENV_BASE_URL)

    with env:
        for index, _task in enumerate(TASKS):
            scores.append(run_task(env, client, index))

    overall = sum(scores) / len(scores) if scores else 0.0
    print(
        json.dumps(
            {
                "benchmark": BENCHMARK,
                "scores": [round(score, 4) for score in scores],
                "overall": round(overall, 4),
            }
        ),
        file=sys.stderr,
        flush=True,
    )


if __name__ == "__main__":
    main()
