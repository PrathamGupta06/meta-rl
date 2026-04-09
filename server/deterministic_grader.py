"""Deterministic grading for K8s architecture tasks."""

from __future__ import annotations

from collections import Counter

try:
    from ..models import GradeIssue, GradeResult, TaskSpec
    from .manifest_parser import ManifestParseError, build_resource_summary, parse_manifest
except ImportError:
    from models import GradeIssue, GradeResult, TaskSpec
    from server.manifest_parser import ManifestParseError, build_resource_summary, parse_manifest


HIGH_PENALTY = 0.18
MEDIUM_PENALTY = 0.10
LOW_PENALTY = 0.05
STRICT_MIN = 0.01
STRICT_MAX = 0.99


def grade_submission(task: TaskSpec, manifest_yaml: str) -> GradeResult:
    """Score a manifest submission against a fixed task spec."""

    try:
        parsed = parse_manifest(manifest_yaml)
    except ManifestParseError as exc:
        issues = [GradeIssue("high", "validity", str(exc))]
        return GradeResult(
            valid=False,
            score_breakdown={
                "validity": STRICT_MIN,
                "topology": STRICT_MIN,
                "security": STRICT_MIN,
                "cost": STRICT_MIN,
            },
            total_score=STRICT_MIN,
            issues=issues,
            resource_summary=[],
            feedback=str(exc),
        )

    issues: list[GradeIssue] = []
    validity_score = _grade_validity(task, parsed, issues)
    topology_score = _grade_topology(task, parsed, issues)
    security_score = _grade_security(task, parsed, issues)
    cost_score = _grade_cost(task, parsed, issues)
    security_score, cost_score = _apply_incomplete_topology_caps(
        topology_score=topology_score,
        security_score=security_score,
        cost_score=cost_score,
    )
    score_breakdown = {
        "validity": _strict_unit_interval(validity_score),
        "topology": _strict_unit_interval(topology_score),
        "security": _strict_unit_interval(security_score),
        "cost": _strict_unit_interval(cost_score),
    }
    total = (
        0.25 * score_breakdown["validity"]
        + 0.35 * score_breakdown["topology"]
        + 0.25 * score_breakdown["security"]
        + 0.15 * score_breakdown["cost"]
    )
    total = _strict_unit_interval(total)
    return GradeResult(
        valid=score_breakdown["validity"] > 0.0,
        score_breakdown=score_breakdown,
        total_score=total,
        issues=issues,
        resource_summary=build_resource_summary(parsed),
        feedback=_render_feedback(score_breakdown, issues),
    )


def _strict_unit_interval(value: float) -> float:
    """Clamp scores into the open interval (0, 1) for validator compatibility."""

    return round(max(STRICT_MIN, min(STRICT_MAX, value)), 4)


def _apply_incomplete_topology_caps(
    topology_score: float,
    security_score: float,
    cost_score: float,
) -> tuple[float, float]:
    """Prevent incomplete manifests from scoring highly on security/cost by omission."""

    if topology_score < 0.15:
        return min(security_score, 0.25), min(cost_score, 0.35)
    if topology_score < 0.35:
        return min(security_score, 0.45), min(cost_score, 0.55)
    return security_score, cost_score


def _grade_validity(task: TaskSpec, parsed, issues: list[GradeIssue]) -> float:
    score = 1.0
    if task.namespace not in parsed.namespaces:
        issues.append(GradeIssue("high", "validity", f"Missing Namespace `{task.namespace}`."))
        score -= HIGH_PENALTY
    if parsed.raw_documents < 3:
        issues.append(GradeIssue("medium", "validity", "Submission should include multiple Kubernetes resources."))
        score -= MEDIUM_PENALTY
    for unsupported in parsed.unsupported_kinds:
        issues.append(GradeIssue("medium", "validity", f"Unsupported kind `{unsupported}` is ignored by the grader."))
        score -= LOW_PENALTY
    for service in parsed.services.values():
        if not service.selector:
            issues.append(
                GradeIssue(
                    "medium",
                    "validity",
                    f"Service `{service.name}` is missing a selector.",
                )
            )
            score -= MEDIUM_PENALTY
        elif not _resolve_service_target(parsed, service.namespace, service.selector):
            issues.append(
                GradeIssue(
                    "high",
                    "validity",
                    f"Service `{service.name}` selector does not match any Deployment labels.",
                )
            )
            score -= HIGH_PENALTY
    return max(0.0, min(1.0, score))


def _grade_topology(task: TaskSpec, parsed, issues: list[GradeIssue]) -> float:
    checks: list[bool] = []
    deployment_by_name = {
        (item.namespace, item.name): item for item in parsed.deployments.values()
    }
    service_by_name = {(item.namespace, item.name): item for item in parsed.services.values()}
    ingress_services = set()
    for ingress in parsed.ingresses.values():
        ingress_services.update(ingress.backends)

    for requirement in task.deployments:
        deployment = deployment_by_name.get((requirement.namespace, requirement.name))
        ok = deployment is not None
        checks.append(ok)
        if not ok:
            issues.append(
                GradeIssue("high", "topology", f"Missing Deployment `{requirement.name}` in namespace `{requirement.namespace}`.")
            )
            continue
        service = service_by_name.get((requirement.namespace, requirement.service_name))
        service_ok = service is not None
        checks.append(service_ok)
        if not service_ok:
            issues.append(
                GradeIssue("high", "topology", f"Missing Service `{requirement.service_name}` for Deployment `{requirement.name}`.")
            )
        if requirement.pvc_name:
            pvc_key = f"{requirement.namespace}/{requirement.pvc_name}"
            pvc_ok = pvc_key in parsed.pvcs and requirement.pvc_name in deployment.volume_claim_names
            checks.append(pvc_ok)
            if not pvc_ok:
                issues.append(
                    GradeIssue(
                        "high",
                        "topology",
                        f"Deployment `{requirement.name}` must mount PVC `{requirement.pvc_name}`.",
                    )
                )

    if task.requires_ingress:
        ingress_ok = bool(parsed.ingresses)
        checks.append(ingress_ok)
        if not ingress_ok:
            issues.append(GradeIssue("high", "topology", "Task requires an Ingress resource."))
        elif not any(req.public and req.name in ingress_services for req in task.services):
            issues.append(
                GradeIssue(
                    "high",
                    "topology",
                    "Ingress must route traffic to the required public service.",
                )
            )
            checks.append(False)
        else:
            checks.append(True)

    for requirement in task.required_hpas:
        hpa_ok = any(key.endswith(f"/{requirement}") for key in parsed.hpas)
        checks.append(hpa_ok)
        if not hpa_ok:
            issues.append(GradeIssue("medium", "topology", f"Missing HPA `{requirement}`."))

    for requirement in task.required_network_policies:
        policy_ok = f"{task.namespace}/{requirement}" in parsed.network_policies
        checks.append(policy_ok)
        if not policy_ok:
            issues.append(
                GradeIssue("medium", "topology", f"Missing NetworkPolicy `{requirement}`.")
            )

    for requirement in task.services:
        service = service_by_name.get((requirement.namespace, requirement.name))
        if not service:
            continue
        service_ok = service.service_type == requirement.service_type
        checks.append(service_ok)
        if not service_ok:
            issues.append(
                GradeIssue(
                    "medium",
                    "topology",
                    f"Service `{requirement.name}` should use type `{requirement.service_type}`.",
                )
            )
        if requirement.public and task.requires_ingress and service.service_type != "ClusterIP":
            issues.append(
                GradeIssue(
                    "medium",
                    "topology",
                    f"Public service `{requirement.name}` should stay `ClusterIP` behind an Ingress.",
                )
            )
            checks.append(False)
        else:
            checks.append(True)

    if not checks:
        return 0.0
    return sum(checks) / len(checks)


def _grade_security(task: TaskSpec, parsed, issues: list[GradeIssue]) -> float:
    score = 1.0
    for deployment in parsed.deployments.values():
        for container in deployment.containers:
            if ":latest" in container.image or ":" not in container.image:
                issues.append(
                    GradeIssue(
                        "high",
                        "security",
                        f"Container `{container.name}` in `{deployment.name}` uses a floating image tag.",
                    )
                )
                score -= HIGH_PENALTY
            if not container.has_requests or not container.has_limits:
                issues.append(
                    GradeIssue(
                        "high",
                        "security",
                        f"Container `{container.name}` in `{deployment.name}` must set requests and limits.",
                    )
                )
                score -= HIGH_PENALTY
            if not container.has_liveness_probe or not container.has_readiness_probe:
                issues.append(
                    GradeIssue(
                        "medium",
                        "security",
                        f"Container `{container.name}` in `{deployment.name}` is missing a liveness or readiness probe.",
                    )
                )
                score -= MEDIUM_PENALTY
            if not container.run_as_non_root:
                issues.append(
                    GradeIssue(
                        "high",
                        "security",
                        f"Container `{container.name}` in `{deployment.name}` must run as non-root.",
                    )
                )
                score -= HIGH_PENALTY
            if not container.read_only_root_fs:
                issues.append(
                    GradeIssue(
                        "medium",
                        "security",
                        f"Container `{container.name}` in `{deployment.name}` should use readOnlyRootFilesystem.",
                    )
                )
                score -= MEDIUM_PENALTY
            if container.allow_privilege_escalation:
                issues.append(
                    GradeIssue(
                        "high",
                        "security",
                        f"Container `{container.name}` in `{deployment.name}` must disable privilege escalation.",
                    )
                )
                score -= HIGH_PENALTY
            if container.privileged:
                issues.append(
                    GradeIssue(
                        "high",
                        "security",
                        f"Container `{container.name}` in `{deployment.name}` must not run privileged.",
                    )
                )
                score -= HIGH_PENALTY

    for service in parsed.services.values():
        if service.name.endswith(("postgres-svc", "redis-svc")) and service.service_type != "ClusterIP":
            issues.append(
                GradeIssue(
                    "high",
                    "security",
                    f"Data service `{service.name}` must not be publicly exposed.",
                )
            )
            score -= HIGH_PENALTY

    for key, configmap in parsed.configmaps.items():
        data = configmap.get("data") or {}
        for item_key in data:
            if any(token in item_key.upper() for token in ("PASSWORD", "SECRET", "TOKEN", "KEY")):
                issues.append(
                    GradeIssue(
                        "medium",
                        "security",
                        f"Sensitive-looking key `{item_key}` appears in ConfigMap `{key}`.",
                    )
                )
                score -= MEDIUM_PENALTY

    if task.required_network_policies and not parsed.network_policies:
        issues.append(
            GradeIssue("high", "security", "Task requires NetworkPolicies but none were provided.")
        )
        score -= HIGH_PENALTY

    return max(0.0, min(1.0, score))


def _grade_cost(task: TaskSpec, parsed, issues: list[GradeIssue]) -> float:
    checks = []
    total_cpu = 0
    total_memory = 0
    total_pvc = 0

    requirement_map = {(item.namespace, item.name): item for item in task.deployments}
    for deployment in parsed.deployments.values():
        requirement = requirement_map.get((deployment.namespace, deployment.name))
        if requirement is None:
            issues.append(
                GradeIssue(
                    "medium",
                    "cost",
                    f"Unexpected Deployment `{deployment.name}` may increase cost without helping the task.",
                )
            )
            checks.append(False)
            continue

        checks.append(requirement.min_replicas <= deployment.replicas <= requirement.max_replicas)
        if not checks[-1]:
            issues.append(
                GradeIssue(
                    "medium",
                    "cost",
                    f"Deployment `{deployment.name}` replica count should stay between {requirement.min_replicas} and {requirement.max_replicas}.",
                )
            )

        for container in deployment.containers:
            total_cpu += container.cpu_millis * max(deployment.replicas, 1)
            total_memory += container.memory_mib * max(deployment.replicas, 1)
            cpu_ok = 0 < container.cpu_millis <= requirement.max_cpu_millis
            mem_ok = 0 < container.memory_mib <= requirement.max_memory_mib
            checks.extend([cpu_ok, mem_ok])
            if not cpu_ok:
                issues.append(
                    GradeIssue(
                        "medium",
                        "cost",
                        f"Container `{container.name}` in `{deployment.name}` is oversized on CPU.",
                    )
                )
            if not mem_ok:
                issues.append(
                    GradeIssue(
                        "medium",
                        "cost",
                        f"Container `{container.name}` in `{deployment.name}` is oversized on memory.",
                    )
                )

    for pvc in parsed.pvcs.values():
        total_pvc += pvc.storage_mib
    for pvc_requirement in task.required_pvcs:
        pvc = parsed.pvcs.get(f"{pvc_requirement.namespace}/{pvc_requirement.name}")
        pvc_ok = pvc is not None and 0 < pvc.storage_mib <= pvc_requirement.max_storage_mib
        checks.append(pvc_ok)
        if not pvc_ok:
            issues.append(
                GradeIssue(
                    "medium",
                    "cost",
                    f"PVC `{pvc_requirement.name}` exceeds the storage budget or is missing.",
                )
            )

    lb_count = Counter(item.service_type for item in parsed.services.values())["LoadBalancer"]
    lb_ok = lb_count <= task.max_load_balancers
    checks.append(lb_ok)
    if not lb_ok:
        issues.append(
            GradeIssue(
                "high",
                "cost",
                f"Submission uses {lb_count} LoadBalancers but task allows at most {task.max_load_balancers}.",
            )
        )

    budget_checks = [
        total_cpu <= task.max_total_cpu_millis,
        total_memory <= task.max_total_memory_mib,
        total_pvc <= task.max_total_pvc_mib,
    ]
    checks.extend(budget_checks)
    if not budget_checks[0]:
        issues.append(
            GradeIssue("medium", "cost", f"Total requested CPU exceeds {task.max_total_cpu_millis}m.")
        )
    if not budget_checks[1]:
        issues.append(
            GradeIssue("medium", "cost", f"Total requested memory exceeds {task.max_total_memory_mib}Mi.")
        )
    if not budget_checks[2]:
        issues.append(
            GradeIssue("medium", "cost", f"Total PVC storage exceeds {task.max_total_pvc_mib}Mi.")
        )

    if not checks:
        return 0.0
    return sum(checks) / len(checks)


def _resolve_service_target(parsed, namespace: str, selector: dict[str, str]) -> str | None:
    for deployment in parsed.deployments.values():
        if deployment.namespace != namespace:
            continue
        if selector.items() <= deployment.labels.items():
            return deployment.name
    return None


def _render_feedback(score_breakdown: dict[str, float], issues: list[GradeIssue]) -> str:
    severity_counts = Counter(issue.severity for issue in issues)
    if not issues:
        return (
            f"Strong submission. Scores: validity={score_breakdown['validity']:.2f}, "
            f"topology={score_breakdown['topology']:.2f}, security={score_breakdown['security']:.2f}, "
            f"cost={score_breakdown['cost']:.2f}."
        )
    top_findings = "; ".join(issue.message for issue in issues[:4])
    return (
        f"Scores: validity={score_breakdown['validity']:.2f}, topology={score_breakdown['topology']:.2f}, "
        f"security={score_breakdown['security']:.2f}, cost={score_breakdown['cost']:.2f}. "
        f"Findings: high={severity_counts['high']}, medium={severity_counts['medium']}, low={severity_counts['low']}. "
        f"Top issues: {top_findings}"
    )
