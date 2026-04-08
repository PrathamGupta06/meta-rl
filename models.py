"""Typed models for the K8s architecture generation environment."""

from dataclasses import dataclass, field

from pydantic import Field

from openenv.core.env_server.types import Action, Observation, State


class KubeArchitectGymAction(Action):
    """A full manifest submission for the active architecture task."""

    manifest_yaml: str = Field(
        ...,
        min_length=1,
        description="Multi-document Kubernetes manifest YAML submitted by the agent.",
    )
    finalize: bool = Field(
        default=False,
        description="Whether the agent wants this submission treated as its final answer.",
    )


class KubeArchitectGymObservation(Observation):
    """Visible feedback returned after each manifest submission."""

    task_id: str = Field(default="", description="Stable benchmark task identifier.")
    task_name: str = Field(default="", description="Human-readable task name.")
    task_brief: str = Field(default="", description="Instructions and constraints for the task.")
    previous_feedback: str = Field(default="", description="Deterministic grader feedback.")
    llm_feedback: str = Field(default="", description="Optional LLM judge feedback.")
    score_breakdown: dict[str, float] = Field(
        default_factory=dict,
        description="Current normalized sub-scores.",
    )
    validation_issues: list[str] = Field(
        default_factory=list,
        description="Current grader findings in plain language.",
    )
    resource_summary: list[str] = Field(
        default_factory=list,
        description="Parsed resource summary for the latest submission.",
    )
    steps_taken: int = Field(default=0, ge=0, description="Number of steps already taken.")
    max_steps: int = Field(default=6, ge=1, description="Episode budget.")
    is_valid_yaml: bool = Field(default=False, description="Whether the manifest parsed successfully.")


class KubeArchitectGymState(State):
    """Environment state tracked across the current episode."""

    task_id: str = Field(default="")
    task_name: str = Field(default="")
    latest_manifest_yaml: str = Field(default="")
    parsed_resource_summary: list[str] = Field(default_factory=list)
    violations: list[str] = Field(default_factory=list)
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    llm_feedback: str = Field(default="")
    current_score: float = Field(default=0.0, ge=0.0, le=1.0)
    is_resolved: bool = Field(default=False)


@dataclass(frozen=True)
class DeploymentRequirement:
    """Expected deployment properties for a benchmark task."""

    name: str
    service_name: str
    namespace: str
    min_replicas: int
    max_replicas: int
    max_cpu_millis: int
    max_memory_mib: int
    public: bool = False
    pvc_name: str | None = None
    needs_hpa: bool = False


@dataclass(frozen=True)
class ServiceRequirement:
    """Expected service properties for a benchmark task."""

    name: str
    namespace: str
    service_type: str
    selector_target: str
    public: bool = False


@dataclass(frozen=True)
class PvcRequirement:
    """Expected persistent volume claim properties."""

    name: str
    namespace: str
    max_storage_mib: int


@dataclass(frozen=True)
class TaskSpec:
    """Static benchmark task definition."""

    task_id: str
    task_name: str
    difficulty: str
    namespace: str
    brief: str
    max_steps: int
    success_threshold: float
    deployments: tuple[DeploymentRequirement, ...]
    services: tuple[ServiceRequirement, ...]
    required_network_policies: tuple[str, ...] = ()
    required_hpas: tuple[str, ...] = ()
    required_pvcs: tuple[PvcRequirement, ...] = ()
    requires_ingress: bool = False
    max_load_balancers: int = 1
    max_total_cpu_millis: int = 3000
    max_total_memory_mib: int = 4096
    max_total_pvc_mib: int = 10240
    required_kinds: tuple[str, ...] = (
        "Namespace",
        "Deployment",
        "Service",
        "Ingress",
        "HorizontalPodAutoscaler",
        "PersistentVolumeClaim",
        "NetworkPolicy",
        "ConfigMap",
        "Secret",
    )


@dataclass
class ParsedContainer:
    """Container-level manifest details used by the grader."""

    name: str
    image: str
    cpu_millis: int
    memory_mib: int
    has_limits: bool
    has_requests: bool
    has_liveness_probe: bool
    has_readiness_probe: bool
    run_as_non_root: bool
    read_only_root_fs: bool
    allow_privilege_escalation: bool
    privileged: bool


@dataclass
class ParsedDeployment:
    """Parsed deployment information."""

    name: str
    namespace: str
    replicas: int
    labels: dict[str, str]
    containers: list[ParsedContainer] = field(default_factory=list)
    volume_claim_names: list[str] = field(default_factory=list)


@dataclass
class ParsedService:
    """Parsed service information."""

    name: str
    namespace: str
    service_type: str
    selector: dict[str, str]
    ports: list[int] = field(default_factory=list)


@dataclass
class ParsedIngress:
    """Parsed ingress information."""

    name: str
    namespace: str
    backends: list[str] = field(default_factory=list)


@dataclass
class ParsedHpa:
    """Parsed autoscaler information."""

    name: str
    namespace: str
    target_deployment: str


@dataclass
class ParsedPvc:
    """Parsed PVC information."""

    name: str
    namespace: str
    storage_mib: int


@dataclass
class ParsedManifest:
    """Normalized resource graph for a manifest submission."""

    namespaces: set[str] = field(default_factory=set)
    deployments: dict[str, ParsedDeployment] = field(default_factory=dict)
    services: dict[str, ParsedService] = field(default_factory=dict)
    ingresses: dict[str, ParsedIngress] = field(default_factory=dict)
    hpas: dict[str, ParsedHpa] = field(default_factory=dict)
    pvcs: dict[str, ParsedPvc] = field(default_factory=dict)
    configmaps: dict[str, dict] = field(default_factory=dict)
    secrets: dict[str, dict] = field(default_factory=dict)
    network_policies: set[str] = field(default_factory=set)
    unsupported_kinds: list[str] = field(default_factory=list)
    raw_documents: int = 0


@dataclass(frozen=True)
class GradeIssue:
    """A deterministic finding produced by the grader."""

    severity: str
    category: str
    message: str


@dataclass
class GradeResult:
    """Deterministic score breakdown and findings."""

    valid: bool
    score_breakdown: dict[str, float]
    total_score: float
    issues: list[GradeIssue]
    resource_summary: list[str]
    feedback: str


@dataclass
class JudgeResult:
    """Optional LLM shaping feedback."""

    shaping_bonus: float = 0.0
    feedback: str = ""
    next_best_fix: str = ""
    raw_score: float = 0.0
