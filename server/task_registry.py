"""Static benchmark tasks for the K8s architecture generation environment."""

from __future__ import annotations

try:
    from ..models import DeploymentRequirement, PvcRequirement, ServiceRequirement, TaskSpec
except ImportError:
    from models import DeploymentRequirement, PvcRequirement, ServiceRequirement, TaskSpec


TASKS: tuple[TaskSpec, ...] = (
    TaskSpec(
        task_id="easy_web_stack",
        task_name="Easy: Public Web App with Private API and Database",
        difficulty="easy",
        namespace="shop",
        max_steps=5,
        success_threshold=0.84,
        deployments=(
            DeploymentRequirement(
                name="frontend",
                service_name="frontend-svc",
                namespace="shop",
                min_replicas=2,
                max_replicas=3,
                max_cpu_millis=500,
                max_memory_mib=512,
                public=True,
            ),
            DeploymentRequirement(
                name="api",
                service_name="api-svc",
                namespace="shop",
                min_replicas=2,
                max_replicas=3,
                max_cpu_millis=750,
                max_memory_mib=768,
            ),
            DeploymentRequirement(
                name="postgres",
                service_name="postgres-svc",
                namespace="shop",
                min_replicas=1,
                max_replicas=1,
                max_cpu_millis=1000,
                max_memory_mib=1024,
                pvc_name="postgres-data",
            ),
        ),
        services=(
            ServiceRequirement(
                name="frontend-svc",
                namespace="shop",
                service_type="LoadBalancer",
                selector_target="frontend",
                public=True,
            ),
            ServiceRequirement(
                name="api-svc",
                namespace="shop",
                service_type="ClusterIP",
                selector_target="api",
            ),
            ServiceRequirement(
                name="postgres-svc",
                namespace="shop",
                service_type="ClusterIP",
                selector_target="postgres",
            ),
        ),
        required_pvcs=(
            PvcRequirement(name="postgres-data", namespace="shop", max_storage_mib=5120),
        ),
        max_load_balancers=1,
        max_total_cpu_millis=2000,
        max_total_memory_mib=2304,
        max_total_pvc_mib=5120,
        brief=(
            "Generate a complete multi-document Kubernetes manifest for a small e-commerce web stack.\n"
            "Requirements:\n"
            "- Create namespace `shop`.\n"
            "- Deploy `frontend`, `api`, and `postgres` in that namespace.\n"
            "- `frontend` must be the only public entrypoint.\n"
            "- `api` and `postgres` must stay internal-only.\n"
            "- `postgres` must use a PVC named `postgres-data`.\n"
            "- Every container must define requests and limits, run as non-root, disable privilege escalation, use a read-only root filesystem, and include liveness/readiness probes.\n"
            "- Avoid `:latest` images and avoid oversized resources.\n"
            "- Use the minimum cost architecture that still meets the availability requirement."
        ),
    ),
    TaskSpec(
        task_id="medium_commerce_stack",
        task_name="Medium: Commerce Platform with Worker, Cache, and HPA",
        difficulty="medium",
        namespace="commerce",
        max_steps=6,
        success_threshold=0.86,
        deployments=(
            DeploymentRequirement(
                name="web",
                service_name="web-svc",
                namespace="commerce",
                min_replicas=2,
                max_replicas=3,
                max_cpu_millis=500,
                max_memory_mib=512,
                public=True,
            ),
            DeploymentRequirement(
                name="api",
                service_name="api-svc",
                namespace="commerce",
                min_replicas=2,
                max_replicas=4,
                max_cpu_millis=1000,
                max_memory_mib=1024,
                needs_hpa=True,
            ),
            DeploymentRequirement(
                name="worker",
                service_name="worker-svc",
                namespace="commerce",
                min_replicas=1,
                max_replicas=2,
                max_cpu_millis=750,
                max_memory_mib=768,
            ),
            DeploymentRequirement(
                name="redis",
                service_name="redis-svc",
                namespace="commerce",
                min_replicas=1,
                max_replicas=1,
                max_cpu_millis=300,
                max_memory_mib=512,
            ),
            DeploymentRequirement(
                name="postgres",
                service_name="postgres-svc",
                namespace="commerce",
                min_replicas=1,
                max_replicas=1,
                max_cpu_millis=1000,
                max_memory_mib=1536,
                pvc_name="postgres-data",
            ),
        ),
        services=(
            ServiceRequirement(
                name="web-svc",
                namespace="commerce",
                service_type="ClusterIP",
                selector_target="web",
                public=True,
            ),
            ServiceRequirement(
                name="api-svc",
                namespace="commerce",
                service_type="ClusterIP",
                selector_target="api",
            ),
            ServiceRequirement(
                name="worker-svc",
                namespace="commerce",
                service_type="ClusterIP",
                selector_target="worker",
            ),
            ServiceRequirement(
                name="redis-svc",
                namespace="commerce",
                service_type="ClusterIP",
                selector_target="redis",
            ),
            ServiceRequirement(
                name="postgres-svc",
                namespace="commerce",
                service_type="ClusterIP",
                selector_target="postgres",
            ),
        ),
        required_network_policies=("deny-db-public", "allow-api-to-db"),
        required_hpas=("api-hpa",),
        required_pvcs=(
            PvcRequirement(name="postgres-data", namespace="commerce", max_storage_mib=8192),
        ),
        requires_ingress=True,
        max_load_balancers=0,
        max_total_cpu_millis=3200,
        max_total_memory_mib=4096,
        max_total_pvc_mib=8192,
        brief=(
            "Generate a secure Kubernetes manifest for a mid-size commerce platform.\n"
            "Requirements:\n"
            "- Create namespace `commerce`.\n"
            "- Deploy `web`, `api`, `worker`, `redis`, and `postgres`.\n"
            "- Expose the application only through an Ingress that routes to `web-svc`.\n"
            "- All Services must be `ClusterIP`; do not use a LoadBalancer.\n"
            "- Add an HPA named `api-hpa` for `api`.\n"
            "- `postgres` must persist data using PVC `postgres-data`.\n"
            "- Add at least two NetworkPolicies named `deny-db-public` and `allow-api-to-db`.\n"
            "- Every workload must have requests/limits, probes, and hardened securityContext.\n"
            "- Optimize for low cost while preserving the required topology."
        ),
    ),
    TaskSpec(
        task_id="hard_control_plane",
        task_name="Hard: Multi-Service Control Plane with Isolation and Cost Caps",
        difficulty="hard",
        namespace="platform",
        max_steps=7,
        success_threshold=0.88,
        deployments=(
            DeploymentRequirement(
                name="gateway",
                service_name="gateway-svc",
                namespace="platform",
                min_replicas=2,
                max_replicas=3,
                max_cpu_millis=500,
                max_memory_mib=512,
                public=True,
            ),
            DeploymentRequirement(
                name="orders-api",
                service_name="orders-api-svc",
                namespace="platform",
                min_replicas=2,
                max_replicas=4,
                max_cpu_millis=800,
                max_memory_mib=768,
                needs_hpa=True,
            ),
            DeploymentRequirement(
                name="payments-api",
                service_name="payments-api-svc",
                namespace="platform",
                min_replicas=2,
                max_replicas=4,
                max_cpu_millis=800,
                max_memory_mib=768,
                needs_hpa=True,
            ),
            DeploymentRequirement(
                name="reporting-worker",
                service_name="reporting-worker-svc",
                namespace="platform",
                min_replicas=1,
                max_replicas=2,
                max_cpu_millis=750,
                max_memory_mib=768,
            ),
            DeploymentRequirement(
                name="redis",
                service_name="redis-svc",
                namespace="platform",
                min_replicas=1,
                max_replicas=1,
                max_cpu_millis=300,
                max_memory_mib=512,
            ),
            DeploymentRequirement(
                name="postgres",
                service_name="postgres-svc",
                namespace="platform",
                min_replicas=1,
                max_replicas=1,
                max_cpu_millis=1200,
                max_memory_mib=1536,
                pvc_name="postgres-data",
            ),
        ),
        services=(
            ServiceRequirement(
                name="gateway-svc",
                namespace="platform",
                service_type="ClusterIP",
                selector_target="gateway",
                public=True,
            ),
            ServiceRequirement(
                name="orders-api-svc",
                namespace="platform",
                service_type="ClusterIP",
                selector_target="orders-api",
            ),
            ServiceRequirement(
                name="payments-api-svc",
                namespace="platform",
                service_type="ClusterIP",
                selector_target="payments-api",
            ),
            ServiceRequirement(
                name="reporting-worker-svc",
                namespace="platform",
                service_type="ClusterIP",
                selector_target="reporting-worker",
            ),
            ServiceRequirement(
                name="redis-svc",
                namespace="platform",
                service_type="ClusterIP",
                selector_target="redis",
            ),
            ServiceRequirement(
                name="postgres-svc",
                namespace="platform",
                service_type="ClusterIP",
                selector_target="postgres",
            ),
        ),
        required_network_policies=(
            "default-deny",
            "allow-gateway-to-apis",
            "allow-apis-to-data",
        ),
        required_hpas=("orders-api-hpa", "payments-api-hpa"),
        required_pvcs=(
            PvcRequirement(name="postgres-data", namespace="platform", max_storage_mib=10240),
        ),
        requires_ingress=True,
        max_load_balancers=0,
        max_total_cpu_millis=4200,
        max_total_memory_mib=5632,
        max_total_pvc_mib=10240,
        brief=(
            "Generate a production-grade Kubernetes manifest for a platform control plane.\n"
            "Requirements:\n"
            "- Create namespace `platform`.\n"
            "- Deploy `gateway`, `orders-api`, `payments-api`, `reporting-worker`, `redis`, and `postgres`.\n"
            "- Expose only `gateway` through an Ingress; all Services must remain `ClusterIP`.\n"
            "- Add HPAs named `orders-api-hpa` and `payments-api-hpa`.\n"
            "- Persist database data with PVC `postgres-data`.\n"
            "- Add NetworkPolicies `default-deny`, `allow-gateway-to-apis`, and `allow-apis-to-data` to isolate east-west traffic.\n"
            "- All containers must be hardened and must avoid `latest` tags, privileged mode, writable root filesystems, and oversized requests.\n"
            "- Stay within a modest resource and storage budget; avoid unnecessary replicas, sidecars, or public load balancers."
        ),
    ),
)


TASK_BY_ID = {task.task_id: task for task in TASKS}


def get_task(task_id: str) -> TaskSpec:
    """Return a benchmark task by id."""

    return TASK_BY_ID[task_id]


def task_ids() -> list[str]:
    """Ordered benchmark ids."""

    return [task.task_id for task in TASKS]
