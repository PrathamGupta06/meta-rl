"""FastAPI application for the K8s architecture generation environment."""

import logging

try:
    from openenv.core.env_server.http_server import create_app

    from ..models import KubeArchitectGymAction, KubeArchitectGymObservation
    from .k8s_architecture_environment import K8sArchitectureEnvironment
except ImportError:
    from openenv.core.env_server.http_server import create_app

    from models import KubeArchitectGymAction, KubeArchitectGymObservation
    from server.k8s_architecture_environment import K8sArchitectureEnvironment

logger = logging.getLogger(__name__)

app = create_app(
    K8sArchitectureEnvironment,
    KubeArchitectGymAction,
    KubeArchitectGymObservation,
    env_name="kube_architect_gym",
    max_concurrent_envs=1,
)


@app.get("/health")
@app.get("/healthz")
async def healthz():
    """Cheap health check that does not need a running episode."""

    try:
        env = K8sArchitectureEnvironment()
        return {
            "status": "ok",
            "task_count": len(env.task_sequence),
            "env_name": "kube_architect_gym",
        }
    except Exception as exc:
        logger.error("Health check failed: %s", exc, exc_info=True)
        return {"status": "error", "error": str(exc)}


def main(host: str = "0.0.0.0", port: int = 8000):
    """Entry point for `uv run server`."""

    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
