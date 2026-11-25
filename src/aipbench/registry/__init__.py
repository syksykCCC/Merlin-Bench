"""Validated task manifests and lazy task-plugin discovery."""

from aipbench.registry.manifest_loader import (
    AuditManifest,
    InstanceManifest,
    ManifestInput,
    ParticipantFeedback,
    PluginManifest,
    ProtocolManifest,
    RandomnessManifest,
    ResourceManifest,
    ScoringManifest,
    TaskManifest,
    load_manifest,
    loads_manifest,
    manifest_digest,
    validate_manifest,
)
from aipbench.registry.task_registry import (
    RegisteredTask,
    TaskFactory,
    TaskRegistry,
    default_registry,
    get_default_registry,
)

__all__ = [
    "AuditManifest",
    "InstanceManifest",
    "ManifestInput",
    "ParticipantFeedback",
    "PluginManifest",
    "ProtocolManifest",
    "RandomnessManifest",
    "RegisteredTask",
    "ResourceManifest",
    "ScoringManifest",
    "TaskFactory",
    "TaskManifest",
    "TaskRegistry",
    "default_registry",
    "get_default_registry",
    "load_manifest",
    "loads_manifest",
    "manifest_digest",
    "validate_manifest",
]
