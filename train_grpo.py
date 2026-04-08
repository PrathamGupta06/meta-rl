"""Minimal GRPO training harness for Kube Architect Gym."""

from __future__ import annotations

import argparse
import re

from datasets import Dataset
from trl import GRPOConfig, GRPOTrainer

from server.deterministic_grader import grade_submission
from server.llm_judge import LLMJudge
from server.task_registry import TASKS, get_task

SYSTEM_PROMPT = """You are a senior platform engineer.
Produce only valid Kubernetes YAML that satisfies the task brief while minimizing security and cost issues.
"""


def extract_manifest(text: str) -> str:
    match = re.search(r"```yaml\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text.strip()


def build_dataset(repeats: int) -> Dataset:
    rows = []
    for _ in range(repeats):
        for task in TASKS:
            rows.append(
                {
                    "prompt": f"{SYSTEM_PROMPT}\n\nTask brief:\n{task.brief}\n\nReturn only Kubernetes YAML.",
                    "task_id": task.task_id,
                }
            )
    return Dataset.from_list(rows)


def make_reward_fn():
    judge = LLMJudge()

    def architecture_reward(completions, task_id, **kwargs):
        rewards = []
        for completion, item_task_id in zip(completions, task_id):
            manifest_yaml = extract_manifest(completion)
            task = get_task(item_task_id)
            grade = grade_submission(task, manifest_yaml)
            judge_result = judge.evaluate(task, manifest_yaml, grade, "")
            reward = max(0.0, min(1.0, grade.total_score + judge_result.shaping_bonus))
            rewards.append(reward)
        return rewards

    return architecture_reward


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a model with GRPO on Kube Architect Gym tasks.")
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--output-dir", default="outputs/grpo-kube-architect")
    parser.add_argument("--dataset-repeats", type=int, default=64)
    parser.add_argument("--learning-rate", type=float, default=1e-5)
    parser.add_argument("--num-train-epochs", type=int, default=1)
    parser.add_argument("--per-device-train-batch-size", type=int, default=1)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=4)
    parser.add_argument("--num-generations", type=int, default=4)
    parser.add_argument("--max-completion-length", type=int, default=2048)
    args = parser.parse_args()

    dataset = build_dataset(args.dataset_repeats)
    train_args = GRPOConfig(
        output_dir=args.output_dir,
        learning_rate=args.learning_rate,
        num_train_epochs=args.num_train_epochs,
        per_device_train_batch_size=args.per_device_train_batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        num_generations=args.num_generations,
        max_completion_length=args.max_completion_length,
        logging_steps=1,
        save_steps=50,
        bf16=True,
        report_to="none",
    )

    trainer = GRPOTrainer(
        model=args.model_name,
        reward_funcs=make_reward_fn(),
        args=train_args,
        train_dataset=dataset,
    )
    trainer.train()
    trainer.save_model(args.output_dir)


if __name__ == "__main__":
    main()
