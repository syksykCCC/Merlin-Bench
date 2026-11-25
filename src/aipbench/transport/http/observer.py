"""Small, public-only summaries for the local Arthur observer page.

The observer deliberately exposes a task-neutral view: one task, one case,
at most two instance features, bounded interaction summaries, elapsed time,
and one official result.  It never serializes instances, certificates,
sum-check coefficients, challenges, or private/audit documents.
"""

from __future__ import annotations

import json
import threading
from collections import deque
from functools import lru_cache
from pathlib import Path
from typing import Any

from aipbench.core.runtime import ArthurRuntime

OBSERVER_SCHEMA_VERSION = "aip-observer/2"
MAX_INTERACTIONS = 12
MAX_TEXT_LENGTH = 120
_HEAD_INTERACTIONS = 2

CASE_TITLES = {
    **{
        (task_id, f"c{index:02d}"): f"C{index:02d}"
        for task_id in (
            "t1.new_maxflow_min_cut",
            "t1.new_weighted_partial_maxsat",
            "t1.new_list_graph_homomorphism",
            "t1.new_structured_closest_vector",
            "t1.new_structured_set_cover",
            "t1.new_rooted_group_steiner_tree",
        )
        for index in range(1, 7)
    },
    **{
        (task_id, f"c{index:02d}"): f"C{index:02d}"
        for task_id in ("t2.new_graph_non_isomorphism",)
        for index in range(1, 8)
    },
    **{
        (task_id, f"c{index:02d}"): f"C{index:02d}"
        for task_id, case_count in (
            ("t2.new_boolean_hypercube_sumcheck", 7),
            ("t2.new_gkr_layered_circuit", 7),
            ("t2.image_size_lower_bound", 6),
            ("t2.new_shamir_tqbf", 6),
            ("t2.new_hamiltonicity_bind_open", 7),
        )
        for index in range(1, case_count + 1)
    },
    **{
        ("t3.machine_checked_mathematics", case_id): title
        for case_id, title in {
            "c01": "Dense binary linear certificate",
            "c02": "Shuffled CRT reconstruction certificate",
            "c03": "Hidden line-graph root certificate",
            "c04": "Anonymous affine-plane decoding certificate",
            "c05": "Anonymous modular column equivalence",
            "c06": "Composite cube-root certificate",
            "c07": "Anonymous modular subset certificate",
            "c08": "Anonymous binary syndrome certificate",
        }.items()
    },
    **{
        ("t3.dafny_verified_programs", case_id): title
        for case_id, title in {
            "c01": "Stable partition preservation",
            "c02": "Boundary-safe lower-bound search",
            "c03": "Capacity-constrained reservation update",
            "c04": "Precedence-constrained earliest schedule",
            "c05": "Dependency-order validation",
            "c06": "Audited priority firewall batch evaluation",
            "c07": "Reference-counted handle-table invariant preservation",
            "c08": "Free-list memory-pool invariant preservation",
        }.items()
    },
    **{
        ("t3.drat_bounded_hardware_safety", case_id): title
        for case_id, title in {
            "c01": "FIFO occupancy safety",
            "c02": "FIFO underflow safety",
            "c03": "Round-robin mutual exclusion",
            "c04": "Round-robin bounded fairness",
            "c05": "Credit-router conservation",
            "c06": "Credit-router forwarding safety",
            "c07": "Pipeline flush-stall safety",
            "c08": "Pipeline writeback consistency",
        }.items()
    },
}


def _object(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _integer(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _short_text(value: object, *, fallback: str = "—") -> str:
    if value is None:
        return fallback
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    if not text:
        return fallback
    if len(text) > MAX_TEXT_LENGTH:
        return text[: MAX_TEXT_LENGTH - 1] + "…"
    return text


def _decimal(value: object) -> str:
    integer = _integer(value)
    return str(integer) if integer is not None else "—"


def _feature(label: str, value: object) -> dict[str, str]:
    return {"label": _short_text(label), "value": _short_text(value)}


def _maxflow_features(instance: dict[str, Any]) -> dict[str, Any]:
    raw_edges = instance.get("edges")
    edge_count = len(raw_edges) if isinstance(raw_edges, list) else 0
    return {
        "kind": "maxflow",
        "features": [
            _feature("Vertices", _decimal(instance.get("num_vertices"))),
            _feature("Directed edges", edge_count),
        ],
    }


def _gni_features(instance: dict[str, Any]) -> dict[str, Any]:
    raw_graphs = instance.get("graphs")
    graph = _object(raw_graphs[0]) if isinstance(raw_graphs, list) and raw_graphs else {}
    raw_edges = graph.get("edges")
    edge_count = len(raw_edges) if isinstance(raw_edges, list) else 0
    return {
        "kind": "graph_non_isomorphism",
        "features": [
            _feature("Vertices per graph", _decimal(graph.get("num_vertices"))),
            _feature("Edges per graph", edge_count),
        ],
    }


def _maxsat_features(instance: dict[str, Any]) -> dict[str, Any]:
    raw_hard = instance.get("hard_clauses")
    raw_soft = instance.get("soft_clauses")
    hard_count = len(raw_hard) if isinstance(raw_hard, list) else 0
    soft_count = len(raw_soft) if isinstance(raw_soft, list) else 0
    return {
        "kind": "weighted_partial_maxsat",
        "features": [
            _feature("Variables", _decimal(instance.get("num_variables"))),
            _feature("Clauses", hard_count + soft_count),
        ],
    }


def _homomorphism_features(instance: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "list_graph_homomorphism",
        "features": [
            _feature("Source vertices", _decimal(instance.get("source_num_vertices"))),
            _feature("Target vertices", _decimal(instance.get("target_num_vertices"))),
        ],
    }


def _group_steiner_features(instance: dict[str, Any]) -> dict[str, Any]:
    raw_groups = instance.get("groups")
    group_count = len(raw_groups) if isinstance(raw_groups, list) else 0
    return {
        "kind": "rooted_group_steiner_tree",
        "features": [
            _feature("Vertices", _decimal(instance.get("num_vertices"))),
            _feature("Groups", group_count),
        ],
    }


def _closest_vector_features(instance: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "structured_closest_vector",
        "features": [
            _feature("Ambient dimension", _decimal(instance.get("ambient_dimension"))),
            _feature("Lattice rank", _decimal(instance.get("rank"))),
        ],
    }


def _set_cover_features(instance: dict[str, Any]) -> dict[str, Any]:
    raw_sets = instance.get("sets")
    set_count = len(raw_sets) if isinstance(raw_sets, list) else 0
    return {
        "kind": "structured_set_cover",
        "features": [
            _feature("Universe elements", _decimal(instance.get("num_elements"))),
            _feature("Candidate sets", set_count),
        ],
    }


def _sumcheck_features(instance: dict[str, Any]) -> dict[str, Any]:
    factors = instance.get("factors")
    return {
        "kind": "boolean_hypercube_sumcheck",
        "features": [
            _feature("Variables", _decimal(instance.get("num_variables"))),
            _feature("Factors", len(factors) if isinstance(factors, list) else 0),
        ],
    }


def _gkr_features(instance: dict[str, Any]) -> dict[str, Any]:
    widths = instance.get("layer_widths")
    width_list = widths if isinstance(widths, list) else []
    return {
        "kind": "gkr_layered_circuit",
        "features": [
            _feature("Layers", max(0, len(width_list) - 1)),
            _feature("Input width", width_list[-1] if width_list else None),
        ],
    }


def _image_size_features(instance: dict[str, Any]) -> dict[str, Any]:
    circuit = _object(instance.get("circuit"))
    return {
        "kind": "image_size_lower_bound",
        "features": [
            _feature("Input bits", _decimal(circuit.get("num_inputs"))),
            _feature("Output bits", _decimal(circuit.get("num_outputs"))),
        ],
    }


def _tqbf_features(instance: dict[str, Any]) -> dict[str, Any]:
    quantifiers = instance.get("quantifiers")
    circuit = _object(instance.get("circuit"))
    gates = circuit.get("gates")
    return {
        "kind": "shamir_tqbf",
        "features": [
            _feature("Quantifiers", len(quantifiers) if isinstance(quantifiers, list) else 0),
            _feature("Circuit gates", len(gates) if isinstance(gates, list) else 0),
        ],
    }


def _hamiltonicity_features(instance: dict[str, Any]) -> dict[str, Any]:
    edges = instance.get("edges")
    return {
        "kind": "hamiltonicity_bind_open",
        "features": [
            _feature("Vertices", _decimal(instance.get("num_vertices"))),
            _feature("Edges", len(edges) if isinstance(edges, list) else 0),
        ],
    }


def _lean_math_features(instance: dict[str, Any]) -> dict[str, Any]:
    raw_features = instance.get("public_features")
    public_features = raw_features if isinstance(raw_features, dict) else {}
    items = list(public_features.items())[:2]
    return {
        "kind": "machine_checked_mathematics",
        "features": [_feature(str(label), value) for label, value in items]
        or [_feature("Proof target", _short_text(instance.get("target_name")))],
    }


def _dafny_features(instance: dict[str, Any]) -> dict[str, Any]:
    raw_features = instance.get("public_features")
    public_features = raw_features if isinstance(raw_features, dict) else {}
    items = list(public_features.items())[:2]
    return {
        "kind": "dafny_verified_programs",
        "features": [_feature(str(label), value) for label, value in items]
        or [_feature("module", _short_text(instance.get("solution_module")))],
    }


def _drat_hardware_features(instance: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "drat_bounded_hardware_safety",
        "features": [
            _feature("Bound", _decimal(instance.get("bound"))),
            _feature("CNF clauses", _decimal(instance.get("num_cnf_clauses"))),
        ],
    }


def _generic_features(instance: dict[str, Any]) -> dict[str, Any]:
    """Safe fallback for future tasks without an observer-specific adapter."""

    return {
        "kind": "generic",
        "features": [_feature("Public fields", len(instance))],
    }


def _agent_summary(kind: str, sequence: int, payload: dict[str, Any]) -> str:
    if kind == "maxflow.certificate":
        edge_flows = payload.get("edge_flows")
        return (
            f"Submitted max-flow/min-cut certificate: value "
            f"{_decimal(payload.get('flow_value'))}, "
            f"{len(edge_flows) if isinstance(edge_flows, list) else 0} edge flows"
        )
    if kind == "gni.begin":
        return "Requested hidden-source challenges from Arthur"
    if kind == "gni.response":
        source_bits = payload.get("source_bits")
        count = len(source_bits) if isinstance(source_bits, list) else 0
        return f"Submitted source classifications ({count} challenge graphs)"
    if kind == "maxsat.assignment":
        assignment = payload.get("assignment")
        count = len(assignment) if isinstance(assignment, list) else 0
        return f"Submitted complete Boolean assignment ({count} variables)"
    if kind == "homomorphism.assignment":
        mapping = payload.get("mapping")
        count = len(mapping) if isinstance(mapping, list) else 0
        return f"Submitted complete graph homomorphism ({count} source vertices)"
    if kind == "group_steiner.edge_set":
        edge_ids = payload.get("edge_ids")
        count = len(edge_ids) if isinstance(edge_ids, list) else 0
        return f"Submitted rooted group-Steiner edge set ({count} edges)"
    if kind == "closest_vector.coefficients":
        coefficients = payload.get("coefficients")
        count = len(coefficients) if isinstance(coefficients, list) else 0
        return f"Submitted lattice coefficient vector ({count} coefficients)"
    if kind == "set_cover.selection":
        set_ids = payload.get("set_ids")
        count = len(set_ids) if isinstance(set_ids, list) else 0
        return f"Submitted set-cover selection ({count} sets)"
    if kind in {"sumcheck.claim", "gkr.claim", "tqbf.claim"}:
        return f"Submitted initial claim (sequence {sequence})"
    if kind in {"sumcheck.poly", "gkr.poly", "tqbf.polynomial"}:
        coefficients = payload.get("coefficients")
        count = len(coefficients) if isinstance(coefficients, list) else 0
        return f"Submitted round polynomial ({count} coefficients)"
    if kind == "gkr.reduce":
        return "Submitted layer-reduction values"
    if kind == "image.begin":
        return "Requested public hash challenge"
    if kind == "image.response":
        preimages = payload.get("preimages")
        count = len(preimages) if isinstance(preimages, list) else 0
        return f"Submitted image preimages ({count} lanes)"
    if kind == "hamiltonicity.commit":
        graphs = payload.get("graphs")
        count = len(graphs) if isinstance(graphs, list) else 0
        return f"Committed to relabeled graphs ({count} lanes)"
    if kind == "hamiltonicity.open":
        openings = payload.get("openings")
        count = len(openings) if isinstance(openings, list) else 0
        return f"Opened graph commitments ({count} lanes)"
    if kind == "lean.proof":
        return "Submitted Lean proof artifact"
    return f"Submitted {_short_text(kind, fallback='unknown message')}"


def _arthur_summary(response: dict[str, Any]) -> tuple[str, str, str | None]:
    status = _short_text(response.get("status"), fallback="PROCESSING")
    reason_value = response.get("reason_code")
    reason = _short_text(reason_value) if reason_value is not None else None
    reply = _object(response.get("reply"))
    reply_kind = _short_text(reply.get("kind"), fallback="")

    if status == "ACCEPT":
        text = "Verification passed; interaction complete"
    elif status in {"REJECT", "TIMEOUT", "SYSTEM_ERROR"}:
        text = "Verification failed"
        if reason is not None:
            text += f" · {reason}"
    elif reply_kind == "gni.challenge":
        text = "Sent a batch of hidden-source challenge graphs"
    elif reply_kind in {
        "sumcheck.ready",
        "sumcheck.challenge",
        "gkr.ready",
        "gkr.challenge",
        "gkr.line_challenge",
        "image.challenge",
        "tqbf.round",
        "tqbf.challenge",
        "hamiltonicity.challenge",
    }:
        text = f"Arthur replied with {_short_text(reply_kind)}"
    elif reply_kind:
        text = f"Replied with {_short_text(reply_kind)}"
    else:
        text = "Message processed"
    return status, text, reason


def _interaction(
    *,
    sequence_value: object,
    kind_value: object,
    payload_value: object,
    response_value: object,
    elapsed_ms: int,
) -> dict[str, Any]:
    kind = _short_text(kind_value, fallback="unknown")
    sequence = _integer(sequence_value) or 0
    status, arthur, reason = _arthur_summary(_object(response_value))
    return {
        "arthur": arthur,
        "elapsed_ms": max(0, elapsed_ms),
        "kind": kind,
        "agent": _agent_summary(kind, sequence, _object(payload_value)),
        "reason_code": reason,
        "sequence": sequence,
        "status": status,
    }


class ObserverEventStore:
    """Thread-safe bounded store containing only pre-summarized interactions."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._head: list[dict[str, Any]] = []
        self._tail: deque[dict[str, Any]] = deque(maxlen=MAX_INTERACTIONS - _HEAD_INTERACTIONS)
        self._total = 0

    def append(
        self,
        *,
        sequence: object,
        kind: object,
        payload: object,
        response: object,
        elapsed_ms: int = 0,
    ) -> None:
        interaction = _interaction(
            sequence_value=sequence,
            kind_value=kind,
            payload_value=payload,
            response_value=response,
            elapsed_ms=elapsed_ms,
        )
        with self._lock:
            self._total += 1
            if len(self._head) < _HEAD_INTERACTIONS:
                self._head.append(interaction)
            else:
                self._tail.append(interaction)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            items = [dict(item) for item in (*self._head, *self._tail)]
            omitted = max(0, self._total - len(items))
            return {
                "items": items,
                "limit": MAX_INTERACTIONS,
                "omitted": omitted,
                "shown": len(items),
                "total": self._total,
                "truncated": bool(omitted),
            }


def _invalid_audit(reason: str) -> dict[str, Any]:
    return {"reason": reason, "state": "INVALID"}


def _audit_summary(path: Path) -> dict[str, Any] | None:
    """Validate an audit document and retain only fields needed for the result."""

    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(decoded, dict):
        return _invalid_audit("AUDIT_DOCUMENT_NOT_OBJECT")

    raw_checks = decoded.get("checks")
    official_result = decoded.get("official_result")
    primary_score = _integer(decoded.get("primary_score"))
    signed_status = decoded.get("signed_terminal_status")
    signing_key_trust = decoded.get("signing_key_trust")
    if (
        decoded.get("schema_version") != "aip-audit/1"
        or not isinstance(raw_checks, list)
        or not raw_checks
        or type(decoded.get("audit_passed")) is not bool
        or official_result not in {"PASS", "FAIL"}
        or primary_score not in {0, 1}
        or signed_status not in {"ACCEPT", "REJECT", "TIMEOUT", "SYSTEM_ERROR"}
        or signing_key_trust not in {"external", "run_directory"}
    ):
        return _invalid_audit("AUDIT_DOCUMENT_SCHEMA_INVALID")

    valid_checks = 0
    for check in raw_checks:
        if (
            not isinstance(check, dict)
            or not isinstance(check.get("name"), str)
            or type(check.get("valid")) is not bool
        ):
            return _invalid_audit("AUDIT_CHECK_SCHEMA_INVALID")
        valid_checks += int(check["valid"] is True)

    audit_passed = decoded["audit_passed"] is True
    expected_result = "PASS" if audit_passed and signed_status == "ACCEPT" else "FAIL"
    expected_score = 1 if expected_result == "PASS" else 0
    if (
        audit_passed != (valid_checks == len(raw_checks))
        or official_result != expected_result
        or primary_score != expected_score
    ):
        return _invalid_audit("AUDIT_RESULT_INCONSISTENT")
    return {
        "official_result": official_result,
        "signed_terminal_status": signed_status,
        "state": "READY",
    }


def _result(terminal: dict[str, Any], audit: dict[str, Any] | None) -> dict[str, Any]:
    if not terminal:
        return {
            "reason_code": None,
            "state": "RUNNING",
            "terminal_status": None,
        }

    terminal_status = _short_text(terminal.get("terminal_status"))
    reason_code = _short_text(terminal.get("reason_code"))
    if audit is None:
        state = "PENDING_AUDIT"
    elif audit.get("state") != "READY":
        state = "INVALID"
        reason_code = _short_text(audit.get("reason"), fallback="AUDIT_INVALID")
    elif audit.get("signed_terminal_status") != terminal_status:
        state = "INVALID"
        reason_code = "AUDIT_TERMINAL_STATUS_MISMATCH"
    else:
        state = "PASS" if audit.get("official_result") == "PASS" else "FAIL"
    return {
        "reason_code": reason_code,
        "state": state,
        "terminal_status": terminal_status,
    }


class ArthurObserver:
    """Read-only model for one task, one case, and one evaluation run."""

    def __init__(self, runtime: ArthurRuntime) -> None:
        self.runtime = runtime
        self.events = ObserverEventStore()
        session = runtime.get_session()
        instance = _object(dict(runtime.get_instance()))
        manifest = _object(dict(runtime.manifest))
        task_id = _short_text(session.get("task_id"))
        case_id = _short_text(session.get("case_id"))
        budgets = _object(session.get("budgets"))

        if task_id == "t1.new_maxflow_min_cut":
            self.instance_summary = _maxflow_features(instance)
        elif task_id == "t1.new_weighted_partial_maxsat":
            self.instance_summary = _maxsat_features(instance)
        elif task_id == "t1.new_list_graph_homomorphism":
            self.instance_summary = _homomorphism_features(instance)
        elif task_id == "t1.new_rooted_group_steiner_tree":
            self.instance_summary = _group_steiner_features(instance)
        elif task_id == "t1.new_structured_closest_vector":
            self.instance_summary = _closest_vector_features(instance)
        elif task_id == "t1.new_structured_set_cover":
            self.instance_summary = _set_cover_features(instance)
        elif task_id == "t2.new_graph_non_isomorphism":
            self.instance_summary = _gni_features(instance)
        elif task_id == "t2.new_boolean_hypercube_sumcheck":
            self.instance_summary = _sumcheck_features(instance)
        elif task_id == "t2.new_gkr_layered_circuit":
            self.instance_summary = _gkr_features(instance)
        elif task_id == "t2.image_size_lower_bound":
            self.instance_summary = _image_size_features(instance)
        elif task_id == "t2.new_shamir_tqbf":
            self.instance_summary = _tqbf_features(instance)
        elif task_id == "t2.new_hamiltonicity_bind_open":
            self.instance_summary = _hamiltonicity_features(instance)
        elif task_id == "t3.machine_checked_mathematics":
            self.instance_summary = _lean_math_features(instance)
        elif task_id == "t3.dafny_verified_programs":
            self.instance_summary = _dafny_features(instance)
        elif task_id == "t3.drat_bounded_hardware_safety":
            self.instance_summary = _drat_hardware_features(instance)
        else:
            self.instance_summary = _generic_features(instance)

        self.task_summary = {
            "case_id": case_id,
            "case_title": CASE_TITLES.get((task_id, case_id), case_id),
            "id": task_id,
            "title": _short_text(manifest.get("title"), fallback=task_id),
        }
        self.wall_budget_ms = (_integer(budgets.get("wall_time_seconds")) or 0) * 1000

    def record(
        self,
        *,
        sequence: object,
        kind: object,
        payload: object,
        response: object,
    ) -> None:
        inputs = self.runtime.observer_inputs()
        elapsed_ms = _integer(inputs.get("elapsed_ms")) or 0
        self.events.append(
            sequence=sequence,
            kind=kind,
            payload=payload,
            response=response,
            elapsed_ms=elapsed_ms,
        )

    def summary(self) -> dict[str, Any]:
        inputs = self.runtime.observer_inputs()
        status = _object(inputs.get("status"))
        terminal = _object(inputs.get("terminal_result"))
        elapsed_ms = _integer(inputs.get("elapsed_ms")) or 0
        terminal_duration = _integer(terminal.get("duration_ms"))
        if terminal_duration is not None:
            elapsed_ms = terminal_duration

        audit = _audit_summary(self.runtime.run_dir / "official" / "audit.json")
        return {
            "conversation": self.events.snapshot(),
            "instance": self.instance_summary,
            "result": _result(terminal, audit),
            "schema_version": OBSERVER_SCHEMA_VERSION,
            "task": self.task_summary,
            "time": {
                "budget_ms": self.wall_budget_ms,
                "elapsed_ms": max(0, elapsed_ms),
                "lifecycle": _short_text(status.get("lifecycle")),
            },
        }


@lru_cache(maxsize=1)
def observer_html() -> str:
    """Load the self-contained observer shell from installed package data."""

    return Path(__file__).with_name("observer.html").read_text(encoding="utf-8")


__all__ = [
    "MAX_INTERACTIONS",
    "OBSERVER_SCHEMA_VERSION",
    "ArthurObserver",
    "ObserverEventStore",
    "observer_html",
]
