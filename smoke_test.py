"""Simple local smoke test for the environment without starting the HTTP server."""

from __future__ import annotations

from server.k8s_architecture_environment import K8sArchitectureEnvironment
from models import KubeArchitectGymAction


GOOD_MANIFEST = """\
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
          ports:
            - containerPort: 80
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


def main() -> None:
    env = K8sArchitectureEnvironment()
    initial = env.reset()
    print(initial.task_id, initial.task_name)
    result = env.step(KubeArchitectGymAction(manifest_yaml=GOOD_MANIFEST, finalize=True))
    print(result.score_breakdown)
    print(result.previous_feedback)


if __name__ == "__main__":
    main()
