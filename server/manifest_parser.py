"""Manifest parsing helpers for the K8s architecture generation environment."""

from __future__ import annotations

from typing import Any

import yaml

try:
    from ..models import (
        ParsedContainer,
        ParsedDeployment,
        ParsedHpa,
        ParsedIngress,
        ParsedManifest,
        ParsedPvc,
        ParsedService,
    )
except ImportError:
    from models import (
        ParsedContainer,
        ParsedDeployment,
        ParsedHpa,
        ParsedIngress,
        ParsedManifest,
        ParsedPvc,
        ParsedService,
    )


class ManifestParseError(ValueError):
    """Raised when a manifest submission cannot be parsed."""


def _parse_cpu_millis(value: Any) -> int:
    if value is None:
        return 0
    text = str(value).strip()
    if text.endswith("m"):
        return int(float(text[:-1]))
    return int(float(text) * 1000)


def _parse_memory_mib(value: Any) -> int:
    if value is None:
        return 0
    text = str(value).strip()
    units = {
        "Ki": 1 / 1024,
        "Mi": 1,
        "Gi": 1024,
        "Ti": 1024 * 1024,
        "K": 1 / 1000,
        "M": 1,
        "G": 1000,
    }
    for suffix, multiplier in units.items():
        if text.endswith(suffix):
            return int(float(text[: -len(suffix)]) * multiplier)
    return int(float(text) / (1024 * 1024))


def parse_manifest(manifest_yaml: str) -> ParsedManifest:
    """Parse multi-document manifest YAML into a normalized graph."""

    if not manifest_yaml.strip():
        raise ManifestParseError("Manifest submission is empty.")

    try:
        documents = [doc for doc in yaml.safe_load_all(manifest_yaml) if doc]
    except yaml.YAMLError as exc:
        raise ManifestParseError(f"YAML parsing failed: {exc}") from exc

    parsed = ParsedManifest(raw_documents=len(documents))
    for doc in documents:
        if not isinstance(doc, dict):
            raise ManifestParseError("Each YAML document must be a mapping.")
        kind = str(doc.get("kind", "")).strip()
        metadata = doc.get("metadata") or {}
        name = str(metadata.get("name", "")).strip()
        namespace = str(metadata.get("namespace", "default")).strip()
        if not kind or not name:
            raise ManifestParseError("Each resource must define kind and metadata.name.")

        if kind == "Namespace":
            parsed.namespaces.add(name)
            continue

        if kind == "Deployment":
            parsed.deployments[f"{namespace}/{name}"] = _parse_deployment(doc, namespace, name)
            continue

        if kind == "Service":
            parsed.services[f"{namespace}/{name}"] = _parse_service(doc, namespace, name)
            continue

        if kind == "Ingress":
            parsed.ingresses[f"{namespace}/{name}"] = _parse_ingress(doc, namespace, name)
            continue

        if kind == "HorizontalPodAutoscaler":
            parsed.hpas[f"{namespace}/{name}"] = _parse_hpa(doc, namespace, name)
            continue

        if kind == "PersistentVolumeClaim":
            parsed.pvcs[f"{namespace}/{name}"] = _parse_pvc(doc, namespace, name)
            continue

        if kind == "ConfigMap":
            parsed.configmaps[f"{namespace}/{name}"] = doc
            continue

        if kind == "Secret":
            parsed.secrets[f"{namespace}/{name}"] = doc
            continue

        if kind == "NetworkPolicy":
            parsed.network_policies.add(f"{namespace}/{name}")
            continue

        parsed.unsupported_kinds.append(kind)

    return parsed


def build_resource_summary(parsed: ParsedManifest) -> list[str]:
    """Produce a compact human-readable summary used in observations."""

    summary: list[str] = []
    if parsed.namespaces:
        summary.append(f"Namespaces: {', '.join(sorted(parsed.namespaces))}")
    if parsed.deployments:
        summary.append(
            "Deployments: "
            + ", ".join(
                f"{item.namespace}/{item.name} x{item.replicas}" for item in parsed.deployments.values()
            )
        )
    if parsed.services:
        summary.append(
            "Services: "
            + ", ".join(
                f"{item.namespace}/{item.name} ({item.service_type})" for item in parsed.services.values()
            )
        )
    if parsed.ingresses:
        summary.append(
            "Ingresses: "
            + ", ".join(f"{item.namespace}/{item.name}" for item in parsed.ingresses.values())
        )
    if parsed.hpas:
        summary.append(
            "HPAs: "
            + ", ".join(f"{item.namespace}/{item.name}" for item in parsed.hpas.values())
        )
    if parsed.pvcs:
        summary.append(
            "PVCs: "
            + ", ".join(
                f"{item.namespace}/{item.name} ({item.storage_mib}Mi)" for item in parsed.pvcs.values()
            )
        )
    if parsed.network_policies:
        summary.append("NetworkPolicies: " + ", ".join(sorted(parsed.network_policies)))
    if parsed.unsupported_kinds:
        summary.append("Unsupported kinds: " + ", ".join(parsed.unsupported_kinds))
    return summary


def _parse_deployment(doc: dict, namespace: str, name: str) -> ParsedDeployment:
    spec = doc.get("spec") or {}
    template = spec.get("template") or {}
    pod_spec = template.get("spec") or {}
    labels = (template.get("metadata") or {}).get("labels") or {}
    containers = []
    for container in pod_spec.get("containers") or []:
        security_context = container.get("securityContext") or {}
        resources = container.get("resources") or {}
        requests = resources.get("requests") or {}
        limits = resources.get("limits") or {}
        cpu_value = requests.get("cpu") or limits.get("cpu")
        memory_value = requests.get("memory") or limits.get("memory")
        containers.append(
            ParsedContainer(
                name=str(container.get("name", "")),
                image=str(container.get("image", "")),
                cpu_millis=_parse_cpu_millis(cpu_value),
                memory_mib=_parse_memory_mib(memory_value),
                has_limits=bool(limits),
                has_requests=bool(requests),
                has_liveness_probe=bool(container.get("livenessProbe")),
                has_readiness_probe=bool(container.get("readinessProbe")),
                run_as_non_root=bool(security_context.get("runAsNonRoot")),
                read_only_root_fs=bool(security_context.get("readOnlyRootFilesystem")),
                allow_privilege_escalation=bool(
                    security_context.get("allowPrivilegeEscalation", False)
                ),
                privileged=bool(security_context.get("privileged", False)),
            )
        )

    volume_claim_names = []
    for volume in pod_spec.get("volumes") or []:
        pvc = volume.get("persistentVolumeClaim")
        if pvc and pvc.get("claimName"):
            volume_claim_names.append(str(pvc["claimName"]))

    return ParsedDeployment(
        name=name,
        namespace=namespace,
        replicas=int(spec.get("replicas", 1)),
        labels={str(k): str(v) for k, v in labels.items()},
        containers=containers,
        volume_claim_names=volume_claim_names,
    )


def _parse_service(doc: dict, namespace: str, name: str) -> ParsedService:
    spec = doc.get("spec") or {}
    selector = {str(k): str(v) for k, v in (spec.get("selector") or {}).items()}
    ports = []
    for port in spec.get("ports") or []:
        target = port.get("targetPort", port.get("port", 0))
        if isinstance(target, int):
            ports.append(target)
    return ParsedService(
        name=name,
        namespace=namespace,
        service_type=str(spec.get("type", "ClusterIP")),
        selector=selector,
        ports=ports,
    )


def _parse_ingress(doc: dict, namespace: str, name: str) -> ParsedIngress:
    spec = doc.get("spec") or {}
    backends: list[str] = []
    for rule in spec.get("rules") or []:
        http = rule.get("http") or {}
        for path in http.get("paths") or []:
            service = (((path.get("backend") or {}).get("service")) or {}).get("name")
            if service:
                backends.append(str(service))
    return ParsedIngress(name=name, namespace=namespace, backends=backends)


def _parse_hpa(doc: dict, namespace: str, name: str) -> ParsedHpa:
    spec = doc.get("spec") or {}
    target = (spec.get("scaleTargetRef") or {}).get("name", "")
    return ParsedHpa(name=name, namespace=namespace, target_deployment=str(target))


def _parse_pvc(doc: dict, namespace: str, name: str) -> ParsedPvc:
    spec = doc.get("spec") or {}
    requests = ((spec.get("resources") or {}).get("requests") or {})
    return ParsedPvc(
        name=name,
        namespace=namespace,
        storage_mib=_parse_memory_mib(requests.get("storage")),
    )
