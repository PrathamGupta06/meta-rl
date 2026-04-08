---
title: Kube Architect Gym
emoji: "🏗️"
colorFrom: blue
colorTo: green
sdk: docker
app_port: 8000
tags:
  - openenv
---

# Kube Architect Gym

`kube_architect_gym` is an OpenEnv environment for training and evaluating agents on a real infrastructure task: generating Kubernetes manifests for microservice architectures under security and cost constraints.

The environment exposes the standard typed OpenEnv `reset()`, `step()`, and `state()` API. Each episode gives the agent a benchmark task brief, accepts a full multi-document manifest submission, and returns deterministic feedback on:

- schema and reference validity
- topology completeness
- security hardening
- cost efficiency

An optional LLM judge can add bounded shaping feedback for training, but final scores are always determined by the built-in deterministic grader.

## Benchmark Tasks

The environment ships with 3 fixed tasks in increasing difficulty:

1. `easy_web_stack`
2. `medium_commerce_stack`
3. `hard_control_plane`

Each task has a deterministic grader with normalized subscores in `[0.0, 1.0]` and an overall score threshold for success.

## Action Space

`KubeArchitectGymAction`

- `manifest_yaml`: full manifest submission
- `finalize`: whether to treat the submission as final

## Observation Space

`KubeArchitectGymObservation`

- `task_id`, `task_name`, `task_brief`
- `previous_feedback`
- `llm_feedback`
- `score_breakdown`
- `validation_issues`
- `resource_summary`
- `steps_taken`, `max_steps`
- `is_valid_yaml`

## State Space

`KubeArchitectGymState`

- `task_id`, `task_name`
- `latest_manifest_yaml`
- `parsed_resource_summary`
- `violations`
- `score_breakdown`
- `llm_feedback`
- `current_score`
- `is_resolved`

## Setup

Install dependencies and run the server:

```bash
uv sync
uv run server
```

Run the local smoke test:

```bash
uv run python smoke_test.py
```

Run the benchmark test file:

```bash
uv run pytest tests/test_env.py -q
```

## Baseline Inference

The hackathon requires a root `inference.py` using the OpenAI client and structured `[START]`, `[STEP]`, and `[END]` logs. This repo provides that script.

To run it against a local server:

```bash
set HF_TOKEN=your-key
set API_BASE_URL=https://your-openai-compatible-endpoint/v1
set MODEL_NAME=your-model
uv run python inference.py
```

To run it against a local Docker image instead of a running server:

```bash
docker build -t kube-architect-gym:test -f server/Dockerfile .
set LOCAL_IMAGE_NAME=kube-architect-gym:test
set HF_TOKEN=your-key
set API_BASE_URL=https://your-openai-compatible-endpoint/v1
set MODEL_NAME=your-model
uv run python inference.py
```

Baseline scores recorded with:

- `API_BASE_URL=https://router.huggingface.co/v1`
- `MODEL_NAME=Qwen/Qwen2.5-72B-Instruct`
- `MAX_REFINEMENT_STEPS=1`
- local Docker image `kube-architect-gym:test`

Observed scores:

- `easy_web_stack`: `0.6186`
- `medium_commerce_stack`: `0.0000`
- `hard_control_plane`: `0.0000`
- overall: `0.2062`

## LLM Judge

The environment can optionally call an OpenAI-compatible judge during `step()` when these environment variables are set:

- `LLM_JUDGE_BASE_URL`
- `LLM_JUDGE_MODEL`
- `LLM_JUDGE_API_KEY` or `OPENAI_API_KEY`

If they are absent, the environment falls back to deterministic-only scoring.

## GRPO Training

`train_grpo.py` provides a minimal GRPO training harness built around the same benchmark tasks and deterministic grader. It is optional and not required for validator execution.

## Deployment

The repo includes:

- `openenv.yaml`
- `Dockerfile`
- root `inference.py`

Typical flow:

```bash
uv run server
openenv validate
openenv push --repo-id your-username/kube-architect-gym
```

For the validator flow, this repo also supports:

```bash
docker build -t kube-architect-gym:test -f server/Dockerfile .
docker run --rm -p 8000:8000 kube-architect-gym:test
```

## Submission Checklist

Before submitting:

- set `API_BASE_URL`
- set `MODEL_NAME`
- set `HF_TOKEN`
- optionally set `LOCAL_IMAGE_NAME` if you want `inference.py` to launch from Docker
- verify `uv run openenv validate --verbose`
- verify `docker build -t kube-architect-gym:test -f server/Dockerfile .`
- verify `uv run python inference.py`
- deploy with `openenv push --repo-id your-username/kube-architect-gym`
