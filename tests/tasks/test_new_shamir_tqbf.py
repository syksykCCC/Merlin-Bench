from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from aipbench.tasks.field61 import MODULUS
from aipbench.tasks.new_shamir_tqbf import (
    CASE_IDS,
    CASE_PARAMETERS,
    TASK_ID,
    TASK_MANIFEST,
    VIRTUAL_AGENTS,
    create_task,
)
from aipbench.tasks.shared.shamir_tqbf import _evaluate_circuit, _parse_public_instance

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_CASES = ("c01", "c02", "c03", "c04", "c05", "c06")
EXPECTED_PROFILES = {
    "c01": (18, 106, 171),
    "c02": (24, 1_594, 300),
    "c03": (24, 802, 300),
    "c04": (44, 195, 990),
    "c05": (44, 234, 990),
    "c06": (44, 277, 990),
}


def _generate(case_id: str, seed: bytes = b"new-shamir-tests"):
    return create_task().generator.generate(
        instance_seed=seed,
        case_id=case_id,
        case_parameters={},
    )


def test_manifest_bundle_and_defaults_are_consistent() -> None:
    assert TASK_ID == "t2.new_shamir_tqbf"
    assert CASE_IDS == EXPECTED_CASES
    assert TASK_MANIFEST["resources"]["wall_time_seconds"] == 600
    assert TASK_MANIFEST["protocol"]["max_events"] == 991
    assert VIRTUAL_AGENTS == {}
    root = ROOT / "tasks" / "tier2_interactive" / "new_shamir_tqbf"
    task_yaml = yaml.safe_load((root / "task.yaml").read_text(encoding="utf-8"))
    assert task_yaml["id"] == TASK_ID
    assert task_yaml["resources"]["wall_time_seconds"] == 600
    for case_id in EXPECTED_CASES:
        case_yaml = yaml.safe_load((root / "cases" / f"{case_id}.yaml").read_text(encoding="utf-8"))
        assert case_yaml["parameters"] == dict(CASE_PARAMETERS[case_id])


@pytest.mark.parametrize("case_id", EXPECTED_CASES)
def test_generators_are_deterministic_seed_sensitive_and_match_profiles(case_id: str) -> None:
    generated = _generate(case_id)
    assert generated == _generate(case_id)
    assert generated.public_instance != _generate(case_id, b"new-shamir-different").public_instance
    assert generated.task_id == TASK_ID
    assert generated.private_instance["truth"] == 1
    metadata = generated.generation_metadata
    assert (
        metadata["num_variables"],
        metadata["num_gates"],
        metadata["num_rounds"],
    ) == EXPECTED_PROFILES[case_id]
    assert metadata["num_rounds"] + 1 <= TASK_MANIFEST["protocol"]["max_events"]


@pytest.mark.parametrize("case_id", EXPECTED_CASES)
def test_protocol_uses_new_identity_schema_and_round_count(case_id: str) -> None:
    generated = _generate(case_id)
    description = create_task().protocol.public_protocol_description(generated_case=generated)
    refs = [
        entry["schema_ref"]
        for group in (description["event_schemas"], description["reply_schemas"])
        for entry in group.values()
    ]
    assert all("/new_shamir_tqbf/" in ref for ref in refs)
    assert description["public_parameters"]["num_rounds"] == EXPECTED_PROFILES[case_id][2]


def test_participant_spec_contains_no_case_family_or_solver_disclosure() -> None:
    spec = (
        ROOT / "tasks" / "tier2_interactive" / "new_shamir_tqbf" / "TASK_SPECIFICATION.md"
    ).read_text(encoding="utf-8")
    lowered = spec.lower()
    forbidden = (
        "branching game",
        "recurrence game",
        "syndrome",
        "safety game",
        "count game",
        "obdd",
        "frontier",
        "dynamic programming",
        "state pair",
        "num_variables=24",
        "affine relation",
        "spectral",
        "fourier",
        "character basis",
        "matrix rank",
        "linear system",
        "reversible map",
        "bijection",
        "triangular map",
        "quadratic tap",
        "component split",
        "local table",
        "block factor",
    )
    assert not any(term in lowered for term in forbidden)


def _wire_values(circuit, assignment: list[int]) -> list[int]:
    wires = [value % MODULUS for value in assignment]
    for gate in circuit.gates:
        op = gate["op"]
        if op == "const":
            value = int(gate["value"])
        elif op == "not":
            value = 1 - wires[int(gate["input"])]
        elif op == "and":
            value = wires[int(gate["left"])] * wires[int(gate["right"])]
        elif op == "or":
            left, right = wires[int(gate["left"])], wires[int(gate["right"])]
            value = left + right - left * right
        elif op == "xor":
            left, right = wires[int(gate["left"])], wires[int(gate["right"])]
            value = left + right - 2 * left * right
        else:
            condition = wires[int(gate["condition"])]
            zero = wires[int(gate["zero"])]
            one = wires[int(gate["one"])]
            value = (1 - condition) * zero + condition * one
        wires.append(value % MODULUS)
    return wires


def _blocked_core(circuit):
    constants = {
        circuit.num_inputs + index: int(gate["value"])
        for index, gate in enumerate(circuit.gates)
        if gate["op"] == "const"
    }
    root = circuit.output
    complement = 0
    while root >= circuit.num_inputs:
        gate = circuit.gates[root - circuit.num_inputs]
        if gate["op"] == "not":
            complement ^= 1
            root = int(gate["input"])
        elif gate["op"] == "and" and constants.get(int(gate["right"])) == 1:
            root = int(gate["left"])
        elif gate["op"] == "and" and constants.get(int(gate["left"])) == 1:
            root = int(gate["right"])
        else:
            break
    assert complement == 0
    outer = circuit.gates[root - circuit.num_inputs]
    assert outer["op"] == "ite" and outer["condition"] == 43
    guard = circuit.gates[int(outer["zero"]) - circuit.num_inputs]
    assert guard["op"] == "ite" and guard["condition"] == 42
    return int(guard["zero"])


def _flatten_and(circuit, wire: int) -> list[int]:
    constants = {
        circuit.num_inputs + index: int(gate["value"])
        for index, gate in enumerate(circuit.gates)
        if gate["op"] == "const"
    }
    root_gate = circuit.gates[wire - circuit.num_inputs] if wire >= circuit.num_inputs else None
    ite_tree = bool(
        root_gate
        and root_gate["op"] == "ite"
        and root_gate["zero"] != root_gate["one"]
        and constants.get(int(root_gate["zero"])) == 0
    )

    def visit(current: int) -> list[int]:
        if current >= circuit.num_inputs:
            gate = circuit.gates[current - circuit.num_inputs]
            if not ite_tree and gate["op"] == "and":
                return visit(int(gate["left"])) + visit(int(gate["right"]))
            if (
                ite_tree
                and gate["op"] == "ite"
                and gate["zero"] != gate["one"]
                and constants.get(int(gate["zero"])) == 0
            ):
                return visit(int(gate["condition"])) + visit(int(gate["one"]))
        return [current]

    return visit(wire)


def _blocked_rows(circuit):
    constants = {
        circuit.num_inputs + index: int(gate["value"])
        for index, gate in enumerate(circuit.gates)
        if gate["op"] == "const"
    }

    def peel_identity(wire: int) -> int:
        while wire >= circuit.num_inputs:
            gate = circuit.gates[wire - circuit.num_inputs]
            if gate["op"] == "not":
                inner = int(gate["input"])
                if inner >= circuit.num_inputs:
                    inner_gate = circuit.gates[inner - circuit.num_inputs]
                    if inner_gate["op"] == "not":
                        wire = int(inner_gate["input"])
                        continue
            elif gate["op"] == "and":
                if constants.get(int(gate["right"])) == 1:
                    wire = int(gate["left"])
                    continue
                if constants.get(int(gate["left"])) == 1:
                    wire = int(gate["right"])
                    continue
            elif gate["op"] == "or":
                if constants.get(int(gate["right"])) == 0:
                    wire = int(gate["left"])
                    continue
                if constants.get(int(gate["left"])) == 0:
                    wire = int(gate["right"])
                    continue
            elif gate["op"] == "ite" and gate["zero"] == gate["one"]:
                wire = int(gate["zero"])
                continue
            break
        return wire

    rows = []
    for cloaked_equality in _flatten_and(circuit, _blocked_core(circuit)):
        equality = peel_identity(cloaked_equality)
        equality_gate = circuit.gates[equality - circuit.num_inputs]
        assert equality_gate["op"] == "not"
        residual = int(equality_gate["input"])
        residual_gate = circuit.gates[residual - circuit.num_inputs]
        assert residual_gate["op"] == "ite"
        output_variable = int(residual_gate["condition"])
        state = int(residual_gate["zero"])
        negated_state = circuit.gates[int(residual_gate["one"]) - circuit.num_inputs]
        assert 21 <= output_variable < 42
        assert negated_state == {"op": "not", "input": state}
        rows.append((equality, residual, output_variable, state))
    assert len(rows) == 21
    return rows


def _structural_supports(circuit) -> list[frozenset[int]]:
    supports = [frozenset({variable}) for variable in range(circuit.num_inputs)]
    for gate in circuit.gates:
        op = gate["op"]
        if op == "const":
            support = frozenset()
        elif op == "not":
            support = supports[int(gate["input"])]
        elif op in ("and", "or", "xor"):
            support = supports[int(gate["left"])] | supports[int(gate["right"])]
        else:
            support = (
                supports[int(gate["condition"])]
                | supports[int(gate["zero"])]
                | supports[int(gate["one"])]
            )
        supports.append(support)
    return supports


@pytest.mark.parametrize("case_id", ("c04", "c05", "c06"))
def test_blocked_tail_has_nonlinear_bijections_and_width_lower_bound(case_id: str) -> None:
    parameters = CASE_PARAMETERS[case_id]
    expected_blocks = sorted(
        (2 * int(parameters["large_block"]), 2 * int(parameters["small_block"]))
    )
    circuit = _parse_public_instance(
        _generate(case_id).public_instance, max_variables=44, max_gates=4_096
    )
    rows = _blocked_rows(circuit)
    supports = _structural_supports(circuit)
    assert all(gate["op"] != "xor" for gate in circuit.gates)

    remaining = set(range(42))
    components: list[set[int]] = []
    row_supports = [set(supports[equality]) for equality, *_ in rows]
    while remaining:
        component = {remaining.pop()}
        changed = True
        while changed:
            changed = False
            for support in row_supports:
                if component & support and not support <= component:
                    component.update(support)
                    remaining.difference_update(support)
                    changed = True
        components.append(component)
    assert sorted(map(len, components)) == expected_blocks

    zero = [0] * 44
    nonlinear_rows = 0
    for _equality, _residual, _output, state in rows:
        inputs = sorted(variable for variable in supports[state] if variable < 21)
        found = False
        base = _wire_values(circuit, zero)[state]
        for left_index, left in enumerate(inputs):
            for right in inputs[left_index + 1 :]:
                left_point = list(zero)
                right_point = list(zero)
                both_point = list(zero)
                left_point[left] = both_point[left] = 1
                right_point[right] = both_point[right] = 1
                derivative = (
                    base
                    ^ _wire_values(circuit, left_point)[state]
                    ^ _wire_values(circuit, right_point)[state]
                    ^ _wire_values(circuit, both_point)[state]
                )
                if derivative:
                    found = True
                    break
            if found:
                break
        nonlinear_rows += int(found)
    assert nonlinear_rows >= 17

    for component in components:
        x_variables = sorted(component & set(range(21)))
        component_rows = [row for row in rows if row[2] in component]
        y_variables = sorted(row[2] for row in component_rows)
        images: set[tuple[int, ...]] = set()
        for mask in range(1 << len(x_variables)):
            assignment = list(zero)
            for index, variable in enumerate(x_variables):
                assignment[variable] = mask >> index & 1
            wires = _wire_values(circuit, assignment)
            image_by_variable = {output: wires[state] for _, _, output, state in component_rows}
            images.add(tuple(image_by_variable[variable] for variable in y_variables))
        assert len(images) == 1 << len(x_variables)
    # The two independent bijections therefore give 2**21 distinct residual
    # functions after the universal block.


@pytest.mark.parametrize("case_id", ("c04", "c05", "c06"))
def test_blocked_tail_field_factorization_and_constructive_strategy(case_id: str) -> None:
    circuit = _parse_public_instance(
        _generate(case_id).public_instance, max_variables=44, max_gates=4_096
    )
    rows = _blocked_rows(circuit)
    predicate = _blocked_core(circuit)
    for sample in range(3):
        values = [
            (pow(17 + sample, index + 1, MODULUS) + 23 * index) % MODULUS for index in range(44)
        ]
        wires = _wire_values(circuit, values)
        factor_product = 1
        for equality, residual, output, state in rows:
            expected_residual = (
                wires[output] + wires[state] - 2 * wires[output] * wires[state]
            ) % MODULUS
            assert wires[residual] == expected_residual
            assert wires[equality] == (1 - expected_residual) % MODULUS
            factor_product = factor_product * wires[equality] % MODULUS
        assert wires[predicate] == factor_product
        u, e = values[-2:]
        guarded = ((1 - u) * factor_product + u) % MODULUS
        expected = (1 - e) * guarded % MODULUS
        assert wires[circuit.output] == expected

    for sample in range(12):
        assignment = [sample >> (index % 4) & 1 for index in range(21)] + [0] * 23
        wires = _wire_values(circuit, assignment)
        for _equality, _residual, output, state in rows:
            assignment[output] = wires[state]
        for wrapper_universal in (0, 1):
            assignment[42] = wrapper_universal
            assignment[43] = 0
            assert _evaluate_circuit(circuit, assignment) == 1
