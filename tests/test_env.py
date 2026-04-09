from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.deterministic_grader import grade_submission
from server.k8s_architecture_environment import K8sArchitectureEnvironment
from server.task_registry import get_task
from models import KubeArchitectGymAction

PARTIAL_MANIFEST = """\
apiVersion: v1
kind: Namespace
metadata:
  name: shop
"""

VALID_MANIFEST = """\
apiVersion: v1
kind: Namespace
metadata:
  name: shop
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
  namespace: shop
spec:
  replicas: 2
  selector:
    matchLabels:
      app: frontend
  template:
    metadata:
      labels:
        app: frontend
    spec:
      containers:
        - name: frontend
          image: nginx:1.25
          resources:
            requests:
              cpu: "200m"
              memory: "256Mi"
            limits:
              cpu: "300m"
              memory: "256Mi"
          securityContext:
            runAsNonRoot: true
            readOnlyRootFilesystem: true
            allowPrivilegeEscalation: false
          livenessProbe:
            httpGet:
              path: /
              port: 80
          readinessProbe:
            httpGet:
              path: /
              port: 80
---
apiVersion: v1
kind: Service
metadata:
  name: frontend-svc
  namespace: shop
spec:
  type: LoadBalancer
  selector:
    app: frontend
  ports:
    - port: 80
      targetPort: 80
"""


def test_invalid_yaml_scores_strictly_between_zero_and_one():
    result = grade_submission(get_task("easy_web_stack"), "not: [valid")
    assert 0.0 < result.total_score < 1.0
    assert not result.valid


def test_incomplete_manifest_does_not_score_high_on_security_or_cost():
    result = grade_submission(get_task("easy_web_stack"), PARTIAL_MANIFEST)
    assert 0.0 < result.score_breakdown["security"] <= 0.25
    assert 0.0 < result.score_breakdown["cost"] <= 0.35
    assert 0.0 < result.total_score < 0.5


def test_env_reset_and_step():
    env = K8sArchitectureEnvironment()
    observation = env.reset()
    assert observation.task_id == "easy_web_stack"
    assert 0.0 < observation.score_breakdown["total"] < 1.0
    assert 0.0 < observation.reward < 1.0

    step_result = env.step(KubeArchitectGymAction(manifest_yaml=VALID_MANIFEST, finalize=True))
    assert "total" in step_result.score_breakdown
    assert step_result.steps_taken == 1
    assert 0.0 < step_result.score_breakdown["total"] < 1.0
    assert 0.0 < step_result.reward < 1.0
