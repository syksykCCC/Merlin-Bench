"""Loading, validation, and canonicalization for task manifests.

The runtime deliberately validates manifests before importing a task plugin.  This
keeps ``task list`` and ``task inspect`` useful even when a plugin has a broken
optional dependency, and gives authors one stable validation boundary.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any, Literal, Self

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    ValidationError,
    field_validator,
    model_validator,
)

from aipbench.core.canonical import digest_json
from aipbench.core.errors import ManifestError


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class PluginManifest(_StrictModel):
    entrypoint: str = Field(min_length=3)

    @field_validator("entrypoint")
    @classmethod
    def validate_entrypoint(cls, value: str) -> str:
        module_name, separator, attribute_name = value.partition(":")
        if (
            separator != ":"
            or not module_name
            or not attribute_name
            or any(not part.isidentifier() for part in module_name.split("."))
            or not attribute_name.isidentifier()
        ):
            raise ValueError("entrypoint must use the form 'package.module:factory'")
        return value


class ParticipantFeedback(_StrictModel):
    dev: Literal["verbose", "minimal"] = "verbose"
    eval: Literal["minimal"] = "minimal"


class ProtocolManifest(_StrictModel):
    api_version: Literal["aip/1"]
    mode: Literal["one_shot", "interactive"]
    public_coin: bool
    one_shot_eval: bool
    max_events: PositiveInt
    participant_feedback: ParticipantFeedback = Field(default_factory=ParticipantFeedback)


class RandomnessManifest(_StrictModel):
    model: Literal["committed_prg", "none"]
    reveal_on_terminal: bool
    domain_separation: Literal["required", "not_applicable"]

    @model_validator(mode="after")
    def validate_randomness_contract(self) -> Self:
        if self.model == "committed_prg":
            if not self.reveal_on_terminal:
                raise ValueError("committed_prg must reveal its seed on terminal")
            if self.domain_separation != "required":
                raise ValueError("committed_prg requires domain separation")
        elif self.reveal_on_terminal or self.domain_separation != "not_applicable":
            raise ValueError(
                "randomness model 'none' requires reveal_on_terminal=false and "
                "domain_separation=not_applicable"
            )
        return self


class InstanceManifest(_StrictModel):
    public_schema: str = Field(min_length=1)
    private_schema: str = Field(min_length=1)


class ResourceManifest(_StrictModel):
    wall_time_seconds: PositiveInt
    cpu_cores: PositiveInt
    memory_mb: PositiveInt
    disk_mb: PositiveInt
    max_artifact_bytes: PositiveInt
    max_events: PositiveInt


class AuditManifest(_StrictModel):
    replay_mode: Literal["strict"]
    require_signature: bool
    require_seed_commitment: bool
    require_instance_digest: bool
    require_event_chain: bool
    require_seed_reveal: bool = False


class ScoringManifest(_StrictModel):
    primary: str = Field(min_length=1)
    partial_progress: str | None = Field(default=None, min_length=1)


class TaskManifest(BaseModel, Mapping[str, Any]):
    """Validated task metadata.

    The object supports both attribute access and the read-only ``Mapping`` API.
    Mapping values are ordinary JSON-compatible values, which makes it convenient
    to hand a manifest to CLI and serialization code without exposing Pydantic
    internals.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: str = Field(pattern=r"^t[1-4]\.[a-z][a-z0-9_]*$")
    version: str = Field(
        pattern=r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
        r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
    )
    tier: int = Field(ge=1, le=4)
    title: str = Field(min_length=1)
    plugin: PluginManifest
    protocol: ProtocolManifest
    randomness: RandomnessManifest
    resources: ResourceManifest
    audit: AuditManifest
    scoring: ScoringManifest
    instance: InstanceManifest | None = None
    soundness: Mapping[str, Any] | None = None
    cases: Mapping[str, Mapping[str, Any]] = Field(default_factory=dict)
    metadata: Mapping[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_cross_section_contracts(self) -> Self:
        if self.protocol.max_events != self.resources.max_events:
            raise ValueError("protocol.max_events must equal resources.max_events")
        if self.protocol.public_coin and self.randomness.model != "committed_prg":
            raise ValueError("public-coin protocols must use committed_prg")
        if self.protocol.mode == "one_shot" and self.protocol.max_events != 1:
            raise ValueError("one_shot protocols must allow exactly one event")
        if self.audit.require_seed_commitment != (self.randomness.model == "committed_prg"):
            raise ValueError(
                "audit.require_seed_commitment must match whether committed_prg is used"
            )
        if self.audit.require_seed_reveal and self.randomness.model != "committed_prg":
            raise ValueError("audit.require_seed_reveal requires committed_prg")
        return self

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)

    def __getitem__(self, key: str) -> Any:
        return self.as_dict()[key]

    def __iter__(self) -> Iterator[str]:  # type: ignore[override]
        return iter(self.as_dict())

    def __len__(self) -> int:
        return len(self.as_dict())


ManifestInput = TaskManifest | Mapping[str, Any]


def validate_manifest(data: ManifestInput, *, source: str | Path | None = None) -> TaskManifest:
    """Validate already-decoded manifest data and normalize validation errors."""

    if isinstance(data, TaskManifest):
        return data
    try:
        return TaskManifest.model_validate(data)
    except ValidationError as exc:
        location = f" in {source}" if source is not None else ""
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors(include_url=False)
        )
        raise ManifestError(f"invalid task manifest{location}: {details}") from exc


def loads_manifest(text: str, *, source: str = "<string>") -> TaskManifest:
    """Load one task manifest from YAML text."""

    try:
        decoded = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ManifestError(f"invalid YAML in {source}: {exc}") from exc
    if not isinstance(decoded, Mapping):
        raise ManifestError(f"task manifest in {source} must be a YAML mapping")
    return validate_manifest(decoded, source=source)


def load_manifest(path: str | Path) -> TaskManifest:
    """Load and validate a UTF-8 YAML task manifest from disk."""

    manifest_path = Path(path)
    try:
        text = manifest_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ManifestError(f"cannot read task manifest {manifest_path}: {exc}") from exc
    return loads_manifest(text, source=str(manifest_path))


def manifest_digest(manifest: ManifestInput) -> str:
    """Return the canonical sha256 identifier of a validated manifest."""

    return digest_json(validate_manifest(manifest).as_dict())
