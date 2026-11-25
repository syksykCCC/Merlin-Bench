"""Public-only hinted reference prover for new Shamir C04--C06.

Run this file with ``--workspace`` pointing at a prepared participant workspace.
The only family hint embodied here is that the reachable core is a product of
two disjoint reversible-map factors followed by the documented asymmetric
forall/exists wrapper.  No private instance or generation seed is read.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

P = (1 << 61) - 1


def wire_values(instance: dict[str, Any], assignment: list[int]) -> list[int]:
    wires = [value % P for value in assignment]
    for gate in instance["circuit"]["gates"]:
        op = gate["op"]
        if op == "const":
            value = gate["value"]
        elif op == "not":
            value = 1 - wires[gate["input"]]
        elif op == "and":
            value = wires[gate["left"]] * wires[gate["right"]]
        elif op == "or":
            left, right = wires[gate["left"]], wires[gate["right"]]
            value = left + right - left * right
        elif op == "xor":
            left, right = wires[gate["left"]], wires[gate["right"]]
            value = left + right - 2 * left * right
        else:
            condition = wires[gate["condition"]]
            zero, one = wires[gate["zero"]], wires[gate["one"]]
            value = (1 - condition) * zero + condition * one
        wires.append(value % P)
    return wires


def peel_core(instance: dict[str, Any]) -> int:
    n = instance["circuit"]["num_inputs"]
    gates = instance["circuit"]["gates"]
    constants = {
        n + index: gate["value"] for index, gate in enumerate(gates) if gate["op"] == "const"
    }
    root = instance["circuit"]["output"]
    complement = 0
    while root >= n:
        gate = gates[root - n]
        if gate["op"] == "not":
            complement ^= 1
            root = gate["input"]
        elif gate["op"] == "and" and constants.get(gate["right"]) == 1:
            root = gate["left"]
        elif gate["op"] == "and" and constants.get(gate["left"]) == 1:
            root = gate["right"]
        else:
            break
    if complement:
        raise ValueError("unexpected complemented padding core")
    outer = gates[root - n]
    if outer["op"] != "ite" or outer["condition"] != 43:
        raise ValueError("blocked wrapper was not found")
    guard = gates[outer["zero"] - n]
    if guard["op"] != "ite" or guard["condition"] != 42:
        raise ValueError("blocked universal guard was not found")
    return guard["zero"]


def flatten_and(instance: dict[str, Any], wire: int) -> list[int]:
    n = instance["circuit"]["num_inputs"]
    gates = instance["circuit"]["gates"]
    constants = {
        n + index: gate["value"] for index, gate in enumerate(gates) if gate["op"] == "const"
    }
    root_gate = gates[wire - n] if wire >= n else None
    ite_tree = bool(
        root_gate
        and root_gate["op"] == "ite"
        and root_gate["zero"] != root_gate["one"]
        and constants.get(root_gate["zero"]) == 0
    )

    def visit(current: int) -> list[int]:
        if current >= n:
            gate = gates[current - n]
            if not ite_tree and gate["op"] == "and":
                return visit(gate["left"]) + visit(gate["right"])
            if (
                ite_tree
                and gate["op"] == "ite"
                and gate["zero"] != gate["one"]
                and constants.get(gate["zero"]) == 0
            ):
                return visit(gate["condition"]) + visit(gate["one"])
        return [current]

    return visit(wire)


def peel_row_identity(instance: dict[str, Any], wire: int) -> int:
    """Peel field-exact row cloaks using public gate syntax only."""

    n = instance["circuit"]["num_inputs"]
    gates = instance["circuit"]["gates"]
    constants = {
        n + index: gate["value"] for index, gate in enumerate(gates) if gate["op"] == "const"
    }
    while wire >= n:
        gate = gates[wire - n]
        if gate["op"] == "not":
            inner = gate["input"]
            if inner >= n and gates[inner - n]["op"] == "not":
                wire = gates[inner - n]["input"]
                continue
        elif gate["op"] == "and":
            if constants.get(gate["right"]) == 1:
                wire = gate["left"]
                continue
            if constants.get(gate["left"]) == 1:
                wire = gate["right"]
                continue
        elif gate["op"] == "or":
            if constants.get(gate["right"]) == 0:
                wire = gate["left"]
                continue
            if constants.get(gate["left"]) == 0:
                wire = gate["right"]
                continue
        elif gate["op"] == "ite" and gate["zero"] == gate["one"]:
            wire = gate["zero"]
            continue
        break
    return wire


def structural_supports(instance: dict[str, Any]) -> list[frozenset[int]]:
    n = instance["circuit"]["num_inputs"]
    supports = [frozenset({variable}) for variable in range(n)]
    for gate in instance["circuit"]["gates"]:
        op = gate["op"]
        if op == "const":
            support = frozenset()
        elif op == "not":
            support = supports[gate["input"]]
        elif op in ("and", "or", "xor"):
            support = supports[gate["left"]] | supports[gate["right"]]
        else:
            support = supports[gate["condition"]] | supports[gate["zero"]] | supports[gate["one"]]
        supports.append(support)
    return supports


@dataclass
class Block:
    x_variables: tuple[int, ...]
    y_variables: tuple[int, ...]
    rows: tuple[tuple[int, int, int, int], ...]
    image: tuple[int, ...]
    support_cache: dict[int, tuple[tuple[int, ...], tuple[int, ...]]]

    def supports(self, stage: int) -> tuple[tuple[int, ...], tuple[int, ...]]:
        cached = self.support_cache.get(stage)
        if cached is not None:
            return cached
        active = tuple(
            variable for variable in sorted(self.x_variables + self.y_variables) if variable < stage
        )
        if stage <= 21:
            result = active, tuple(range(1 << len(active)))
        else:
            y_positions = {variable: index for index, variable in enumerate(self.y_variables)}
            supports: list[int] = []
            for x_mask, y_mask in enumerate(self.image):
                value = 0
                for position, variable in enumerate(active):
                    if variable < 21:
                        bit = x_mask >> self.x_variables.index(variable) & 1
                    else:
                        bit = y_mask >> y_positions[variable] & 1
                    value |= bit << position
                supports.append(value)
            result = active, tuple(supports)
        self.support_cache[stage] = result
        return result


def extract_blocks(instance: dict[str, Any]) -> tuple[Block, Block]:
    n = instance["circuit"]["num_inputs"]
    gates = instance["circuit"]["gates"]
    supports = structural_supports(instance)
    rows: list[tuple[int, int, int, int]] = []
    for cloaked_equality in flatten_and(instance, peel_core(instance)):
        equality = peel_row_identity(instance, cloaked_equality)
        equality_gate = gates[equality - n]
        residual = equality_gate["input"]
        residual_gate = gates[residual - n]
        output = residual_gate["condition"]
        state = residual_gate["zero"]
        if equality_gate["op"] != "not" or residual_gate["op"] != "ite" or not 21 <= output < 42:
            raise ValueError("blocked equality row was not found")
        rows.append((equality, residual, output, state))
    if len(rows) != 21:
        raise ValueError("expected 21 blocked equality rows")

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
    if sorted(map(len, components)) not in ([18, 24], [20, 22]):
        raise ValueError("unexpected blocked component sizes")

    blocks: list[Block] = []
    for component in sorted(components, key=len, reverse=True):
        x_variables = tuple(sorted(component & set(range(21))))
        component_rows = tuple(row for row in rows if row[2] in component)
        y_variables = tuple(sorted(row[2] for row in component_rows))
        row_by_y = {row[2]: row for row in component_rows}
        image: list[int] = []
        for x_mask in range(1 << len(x_variables)):
            assignment = [0] * 44
            for position, variable in enumerate(x_variables):
                assignment[variable] = x_mask >> position & 1
            wires = wire_values(instance, assignment)
            y_mask = 0
            for position, variable in enumerate(y_variables):
                y_mask |= int(wires[row_by_y[variable][3]]) << position
            image.append(y_mask)
        if len(set(image)) != 1 << len(x_variables):
            raise ValueError("public blocked map is not bijective")
        blocks.append(Block(x_variables, y_variables, component_rows, tuple(image), {}))
    return blocks[0], blocks[1]


def project_branch(
    active: tuple[int, ...], supports: tuple[int, ...], variable: int, bit: int
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    position = active.index(variable)
    low_mask = (1 << position) - 1
    projected = tuple(
        (value & low_mask) | ((value >> 1) & ~low_mask)
        for value in supports
        if value >> position & 1 == bit
    )
    return active[:position] + active[position + 1 :], projected


def coordinate(coords: list[int], variable: int, target: int, value: int) -> int:
    return value if variable == target else coords[variable]


def single_eval(
    active: tuple[int, ...],
    supports: tuple[int, ...],
    coords: list[int],
    target: int,
    target_value: int,
) -> int:
    total = 0
    for support in supports:
        weight = 1
        for position, variable in enumerate(active):
            point = coordinate(coords, variable, target, target_value)
            factor = point if support >> position & 1 else 1 - point
            weight = weight * factor % P
        total = (total + weight) % P
    return total


def pair_partial_eval(
    left_supports: tuple[int, ...],
    right_supports: tuple[int, ...],
    active: tuple[int, ...],
    threshold: int,
    coords: list[int],
    target: int,
    target_value: int,
) -> int:
    suffix_positions = [
        position for position, variable in enumerate(active) if variable > threshold
    ]
    prefix_positions = [
        position for position, variable in enumerate(active) if variable <= threshold
    ]

    def grouped(supports: tuple[int, ...]) -> dict[int, int]:
        groups: dict[int, int] = {}
        for support in supports:
            key = 0
            for key_position, position in enumerate(suffix_positions):
                key |= (support >> position & 1) << key_position
            weight = 1
            for position in prefix_positions:
                variable = active[position]
                point = coordinate(coords, variable, target, target_value)
                factor = point if support >> position & 1 else 1 - point
                weight = weight * factor % P
            groups[key] = (groups.get(key, 0) + weight) % P
        return groups

    left = grouped(left_supports)
    right = grouped(right_supports)
    total = 0
    for key, left_value in left.items():
        right_value = right.get(key)
        if right_value is None:
            continue
        weight = 1
        for key_position, position in enumerate(suffix_positions):
            point = coords[active[position]]
            factor = point if key >> key_position & 1 else 1 - point
            weight = weight * factor % P
        total = (total + left_value * right_value * weight) % P
    return total


def interpolate(values: list[int]) -> list[int]:
    size = len(values)
    matrix = [
        [pow(row, column, P) for column in range(size)] + [values[row] % P] for row in range(size)
    ]
    for column in range(size):
        pivot = next(row for row in range(column, size) if matrix[row][column])
        matrix[column], matrix[pivot] = matrix[pivot], matrix[column]
        inverse = pow(matrix[column][column], P - 2, P)
        matrix[column] = [value * inverse % P for value in matrix[column]]
        for row in range(size):
            if row == column:
                continue
            scale = matrix[row][column]
            if scale:
                matrix[row] = [
                    (left - scale * right) % P
                    for left, right in zip(matrix[row], matrix[column], strict=True)
                ]
    return [matrix[row][-1] for row in range(size)]


def block_factor_value(instance: dict[str, Any], block: Block, assignment: list[int]) -> int:
    wires = wire_values(instance, assignment)
    value = 1
    for equality, *_ in block.rows:
        value = value * wires[equality] % P
    return value


def partial_circuit_block(
    instance: dict[str, Any],
    block: Block,
    coords: list[int],
    threshold: int,
    target: int,
    target_value: int,
) -> int:
    suffix = tuple(variable for variable in block.x_variables if variable > threshold)
    total = 0
    for suffix_mask in range(1 << len(suffix)):
        assignment = list(coords)
        assignment[target] = target_value
        weight = 1
        for position, variable in enumerate(suffix):
            bit = suffix_mask >> position & 1
            point = coords[variable]
            weight = weight * (point if bit else 1 - point) % P
            assignment[variable] = bit
        total = (total + weight * block_factor_value(instance, block, assignment)) % P
    return total


class Prover:
    def __init__(self, instance: dict[str, Any]) -> None:
        self.instance = instance
        self.blocks = extract_blocks(instance)
        self.coords = [0] * 44

    def mle_product(self, stage: int, target: int, value: int) -> int:
        result = 1
        for block in self.blocks:
            active, supports = block.supports(stage)
            result = result * single_eval(active, supports, self.coords, target, value) % P
        return result

    def y_reduction_value(self, stage: int, target: int, value: int) -> int:
        q = stage - 1
        q_block = next(block for block in self.blocks if q in block.y_variables)
        other = next(block for block in self.blocks if block is not q_block)
        q_active, q_supports = q_block.supports(stage)
        branch_active, left = project_branch(q_active, q_supports, q, 0)
        _, right = project_branch(q_active, q_supports, q, 1)
        other_active, other_supports = other.supports(stage)
        other_single = single_eval(other_active, other_supports, self.coords, target, value)
        left_single = single_eval(branch_active, left, self.coords, target, value)
        right_single = single_eval(branch_active, right, self.coords, target, value)
        q_pair = pair_partial_eval(left, right, branch_active, target, self.coords, target, value)
        other_pair = pair_partial_eval(
            other_supports,
            other_supports,
            other_active,
            target,
            self.coords,
            target,
            value,
        )
        return (other_single * (left_single + right_single) - q_pair * other_pair) % P

    def y_quantifier(self, stage: int) -> list[int]:
        q = stage - 1
        q_block = next(block for block in self.blocks if q in block.y_variables)
        other = next(block for block in self.blocks if block is not q_block)
        q_active, q_supports = q_block.supports(stage)
        branch_active, left = project_branch(q_active, q_supports, q, 0)
        _, right = project_branch(q_active, q_supports, q, 1)
        other_active, other_supports = other.supports(stage)
        other_value = single_eval(other_active, other_supports, self.coords, q, 0)
        left_value = single_eval(branch_active, left, self.coords, q, 0)
        right_value = single_eval(branch_active, right, self.coords, q, 0)
        h0 = left_value * other_value % P
        h1 = right_value * other_value % P
        return [h0, (h1 - h0) % P]

    def polynomial(self, round_spec: dict[str, Any]) -> list[int]:
        stage = round_spec["stage"]
        operator = round_spec["operator"]
        variable = round_spec["variable"]
        bound = round_spec["degree_bound"]
        if stage <= 21:
            coefficients = [1]
        elif stage <= 42:
            if operator == "reduce":
                coefficients = interpolate(
                    [self.y_reduction_value(stage, variable, point) for point in range(3)]
                )
            else:
                coefficients = self.y_quantifier(stage)
        elif stage == 43:
            if operator == "reduce":
                h0 = self.mle_product(42, variable, 0)
                h1 = self.mle_product(42, variable, 1)
                coefficients = [h0, (h1 - h0) % P]
            else:
                f_value = self.mle_product(42, variable, 0)
                coefficients = [f_value, (1 - f_value) % P]
        else:
            if operator == "reduce" and variable < 42:
                values = []
                for point in range(bound + 1):
                    factor = 1
                    for block in self.blocks:
                        factor = (
                            factor
                            * partial_circuit_block(
                                self.instance,
                                block,
                                self.coords,
                                variable,
                                variable,
                                point,
                            )
                            % P
                        )
                    values.append(((1 - self.coords[42]) * factor + self.coords[42]) % P)
                coefficients = interpolate(values)
            elif operator == "reduce":
                factor = 1
                for block in self.blocks:
                    factor = (
                        factor
                        * partial_circuit_block(self.instance, block, self.coords, 42, 42, 0)
                        % P
                    )
                coefficients = [factor, (1 - factor) % P]
            else:
                wires = wire_values(self.instance, self.coords)
                predicate = wires[peel_core(self.instance)]
                guarded = ((1 - self.coords[42]) * predicate + self.coords[42]) % P
                coefficients = [guarded, (-guarded) % P]
        if len(coefficients) > bound + 1 and any(coefficients[bound + 1 :]):
            raise ValueError("reference polynomial exceeded the public degree bound")
        return coefficients[: bound + 1] + [0] * (bound + 1 - len(coefficients))


def durable(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    sys.path.insert(0, str(workspace))
    spec = importlib.util.spec_from_file_location(
        "blocked_agent_client", workspace / "agent_client.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load agent_client.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    client = module.AgentClient.from_environment(
        connection_file=workspace / ".aipbench-connection.json", timeout_seconds=30
    )
    instance = json.loads((workspace / "instance.json").read_text(encoding="utf-8"))
    prover = Prover(instance)
    transcript = workspace / "reference_responses.jsonl"
    start = time.monotonic()
    session = client.get("session")
    session_id = session["session_id"]
    sequence = 0

    def submit(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        nonlocal sequence
        body = {
            "api_version": "aip/1",
            "session_id": session_id,
            "sequence": sequence,
            "kind": kind,
            "payload": payload,
            "artifact_refs": [],
        }
        response = client.request_json("POST", "/v1/events", json_body=body)
        with transcript.open("ab") as handle:
            line = json.dumps(response, separators=(",", ":")).encode() + b"\n"
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
        sequence += 1
        return response

    response = submit("tqbf.claim", {"value": "0000000000000001"})
    if response["status"] != "CONTINUE":
        raise RuntimeError(f"claim failed: {response}")
    round_spec = response["reply"]["payload"]["round"]
    while True:
        coefficients = prover.polynomial(round_spec)
        response = submit(
            "tqbf.polynomial",
            {
                "round_index": round_spec["round_index"],
                "coefficients": [f"{value:016x}" for value in coefficients],
            },
        )
        if response["status"] != "CONTINUE":
            elapsed = time.monotonic() - start
            result = {
                "status": response["status"],
                "reason_code": response.get("reason_code"),
                "events": sequence,
                "elapsed_seconds": elapsed,
            }
            durable(
                workspace / "reference_result.json",
                json.dumps(result, indent=2).encode(),
            )
            print(json.dumps(result))
            return 0 if response["status"] == "ACCEPT" else 1
        challenge = response["reply"]["payload"]
        prover.coords[round_spec["variable"]] = int(challenge["point"], 16)
        round_spec = challenge["next_round"]


if __name__ == "__main__":
    raise SystemExit(main())
