"""Task plugin registry with lazy entry-point imports."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, cast

from aipbench.core.errors import ManifestError
from aipbench.core.protocol import TaskPlugin
from aipbench.registry.manifest_loader import (
    ManifestInput,
    TaskManifest,
    load_manifest,
    validate_manifest,
)

TaskFactory = Callable[[], TaskPlugin]


@dataclass(frozen=True)
class RegisteredTask:
    manifest: TaskManifest
    factory: TaskFactory | None = None


class TaskRegistry:
    """Validated registry used by the runtime and CLI.

    Registration never imports plugin code. ``get`` resolves a configured entry
    point on first use and caches the resulting stateless plugin object.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, RegisteredTask] = {}
        self._plugins: dict[str, TaskPlugin] = {}

    def register(
        self,
        manifest: ManifestInput,
        factory: TaskFactory | None = None,
        *,
        replace: bool = False,
    ) -> None:
        validated = validate_manifest(manifest)
        if validated.id in self._tasks and not replace:
            raise ManifestError(f"task is already registered: {validated.id}")
        self._tasks[validated.id] = RegisteredTask(validated, factory)
        self._plugins.pop(validated.id, None)

    def unregister(self, task_id: str) -> None:
        if task_id not in self._tasks:
            raise KeyError(f"unknown task: {task_id}")
        del self._tasks[task_id]
        self._plugins.pop(task_id, None)

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._tasks))

    def list(self) -> tuple[dict[str, Any], ...]:
        """Return serializable manifests in stable task-id order."""

        return tuple(self._tasks[task_id].manifest.as_dict() for task_id in self.ids())

    def list_tasks(self) -> tuple[dict[str, Any], ...]:
        return self.list()

    def inspect(self, task_id: str) -> dict[str, Any]:
        return self.get_manifest(task_id).as_dict()

    def get_manifest(self, task_id: str) -> TaskManifest:
        try:
            return self._tasks[task_id].manifest
        except KeyError as exc:
            raise KeyError(f"unknown task: {task_id}") from exc

    def get(self, task_id: str) -> TaskPlugin:
        """Create (once), validate, and return a task plugin."""

        self.get_manifest(task_id)
        cached = self._plugins.get(task_id)
        if cached is not None:
            return cached

        record = self._tasks[task_id]
        factory = record.factory or self._load_factory(record.manifest.plugin.entrypoint)
        plugin = factory()
        self._validate_plugin(task_id, record.manifest, plugin)
        self._plugins[task_id] = plugin
        return plugin

    def create_task(self, task_id: str) -> TaskPlugin:
        return self.get(task_id)

    def __contains__(self, task_id: object) -> bool:
        return task_id in self._tasks

    def __iter__(self) -> Iterator[str]:
        return iter(self.ids())

    def __len__(self) -> int:
        return len(self._tasks)

    @staticmethod
    def _load_factory(entrypoint: str) -> TaskFactory:
        module_name, _, attribute_name = entrypoint.partition(":")
        try:
            module = import_module(module_name)
        except (ImportError, ModuleNotFoundError) as exc:
            raise ManifestError(f"cannot import task plugin module {module_name}: {exc}") from exc
        try:
            factory = getattr(module, attribute_name)
        except AttributeError as exc:
            raise ManifestError(f"task entrypoint does not exist: {entrypoint}") from exc
        if not callable(factory):
            raise ManifestError(f"task entrypoint is not callable: {entrypoint}")
        return cast(TaskFactory, factory)

    @staticmethod
    def _validate_plugin(
        task_id: str, registered_manifest: TaskManifest, plugin: TaskPlugin
    ) -> None:
        plugin_manifest_data = getattr(plugin, "manifest", None)
        if not isinstance(plugin_manifest_data, Mapping):
            raise ManifestError(f"task plugin {task_id} does not expose a manifest mapping")
        plugin_manifest = validate_manifest(
            plugin_manifest_data, source=registered_manifest.plugin.entrypoint
        )
        if plugin_manifest.id != task_id:
            raise ManifestError(
                f"task plugin identity mismatch: expected {task_id}, got {plugin_manifest.id}"
            )
        if plugin_manifest.version != registered_manifest.version:
            raise ManifestError(
                "task plugin version mismatch: "
                f"expected {registered_manifest.version}, got {plugin_manifest.version}"
            )
        if plugin_manifest.as_dict() != registered_manifest.as_dict():
            raise ManifestError(
                f"task plugin manifest does not match its registered manifest: {task_id}"
            )


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

# Fixed benchmark inventory: 15 tasks and 100 cases.
_BUILTIN_MANIFEST_PATHS = (
    "tasks/tier1_np/new_maxflow_min_cut/task.yaml",
    "tasks/tier1_np/new_weighted_partial_maxsat/task.yaml",
    "tasks/tier1_np/new_structured_set_cover/task.yaml",
    "tasks/tier1_np/new_structured_closest_vector/task.yaml",
    "tasks/tier1_np/new_list_graph_homomorphism/task.yaml",
    "tasks/tier1_np/new_rooted_group_steiner_tree/task.yaml",
    "tasks/tier2_interactive/new_graph_non_isomorphism/task.yaml",
    "tasks/tier2_interactive/new_boolean_hypercube_sumcheck/task.yaml",
    "tasks/tier2_interactive/new_gkr_layered_circuit/task.yaml",
    "tasks/tier2_interactive/image_size_lower_bound/task.yaml",
    "tasks/tier2_interactive/new_shamir_tqbf/task.yaml",
    "tasks/tier2_interactive/new_hamiltonicity_bind_open/task.yaml",
    "tasks/tier3_applied/machine_checked_mathematics/task.yaml",
    "tasks/tier3_applied/dafny_verified_programs/task.yaml",
    "tasks/tier3_applied/drat_bounded_hardware_safety/task.yaml",
)


def _builtin_manifests() -> tuple[TaskManifest, ...]:
    """Load current manifests without importing task implementations."""

    manifests: list[TaskManifest] = []
    for relative_path in _BUILTIN_MANIFEST_PATHS:
        manifest = load_manifest(_REPOSITORY_ROOT / relative_path)
        data = manifest.as_dict()
        task_directory = Path(relative_path).parent
        instance = data.get("instance")
        if isinstance(instance, dict):
            for visibility in ("public_schema", "private_schema"):
                schema_path = instance.get(visibility)
                if isinstance(schema_path, str):
                    instance[visibility] = (task_directory / schema_path).as_posix()
        manifests.append(validate_manifest(data, source=relative_path))
    return tuple(manifests)


def default_registry() -> TaskRegistry:
    """Build a registry containing the current public benchmark tasks."""

    registry = TaskRegistry()
    for manifest in _builtin_manifests():
        registry.register(manifest)
    return registry


def get_default_registry() -> TaskRegistry:
    """Compatibility alias for callers that prefer an explicit getter name."""

    return default_registry()
