"""Structured 18--44 variable builders for the new Shamir-TQBF task."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Final

from aipbench.tasks.shared.tqbf_cases.common import (
    CircuitBuilder,
    TQBFBlueprint,
    add_semantic_padding,
)


class DeterministicStream:
    def __init__(self, seed: bytes, case_id: str) -> None:
        self.seed = hashlib.sha256(b"aipbench/new-tqbf/" + case_id.encode() + seed).digest()
        self.counter = 0

    def randbelow(self, upper: int) -> int:
        if upper <= 0:
            raise ValueError("upper must be positive")
        while True:
            block = hashlib.sha256(self.seed + self.counter.to_bytes(8, "big")).digest()
            self.counter += 1
            value = int.from_bytes(block, "big")
            limit = (1 << 256) - ((1 << 256) % upper)
            if value < limit:
                return value % upper

    def shuffle(self, values: list[int]) -> None:
        for index in range(len(values) - 1, 0, -1):
            chosen = self.randbelow(index + 1)
            values[index], values[chosen] = values[chosen], values[index]


def integer_parameter(
    parameters: Mapping[str, object], name: str, *, minimum: int, maximum: int
) -> int:
    value = parameters.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return value


def branching_program_blueprint(
    *,
    seed: bytes,
    case_id: str,
    quantifiers: Sequence[str],
    state_count: int,
    initial_state: int,
    transitions: Sequence[Sequence[tuple[int, int]]],
    accepting_states: set[int],
    family: str,
) -> TQBFBlueprint:
    num_inputs = len(quantifiers)
    if len(transitions) != num_inputs:
        raise ValueError("one transition layer is required per variable")
    builder = CircuitBuilder(num_inputs)
    accept = builder.const(1)
    reject = builder.const(0)
    layer = [accept if state in accepting_states else reject for state in range(state_count)]
    for variable in range(num_inputs - 1, -1, -1):
        if len(transitions[variable]) != state_count:
            raise ValueError("transition layer has the wrong width")
        next_layer: list[int] = []
        for zero_state, one_state in transitions[variable]:
            if not 0 <= zero_state < state_count or not 0 <= one_state < state_count:
                raise ValueError("transition leaves the state space")
            next_layer.append(builder.ite(variable, layer[zero_state], layer[one_state]))
        layer = next_layer
    output = add_semantic_padding(builder, layer[initial_state], seed=seed, case_id=case_id)
    return TQBFBlueprint(
        quantifiers=tuple(quantifiers),
        gates=tuple(builder.gates),
        output=output,
        family=family,
    )


def width_four_response_game(seed: bytes, *, pairs: int) -> TQBFBlueprint:
    state_count = 4
    transitions: list[list[tuple[int, int]]] = []
    for variable in range(2 * pairs):
        universal_move = variable % 2 == 0
        layer: list[tuple[int, int]] = []
        for state in range(state_count):
            if universal_move:
                layer.append((1, 2) if state == 0 else (3, 3))
            elif state == 1:
                layer.append((0, 3))
            elif state == 2:
                layer.append((3, 0))
            else:
                layer.append((3, 3))
        transitions.append(layer)
    return branching_program_blueprint(
        seed=seed,
        case_id="c01",
        quantifiers=tuple(value for _ in range(pairs) for value in ("forall", "exists")),
        state_count=state_count,
        initial_state=0,
        transitions=transitions,
        accepting_states={0},
        family="width4_alternating_response_game",
    )


def recurrence_game(seed: bytes, *, pairs: int, memory: int) -> TQBFBlueprint:
    memories = 1 << memory
    pending_offset = memories
    sink = 2 * memories
    state_count = sink + 1
    mask = memories - 1
    transitions: list[list[tuple[int, int]]] = []
    for variable in range(2 * pairs):
        layer: list[tuple[int, int]] = []
        if variable % 2 == 0:
            for state in range(state_count):
                if state < memories:
                    layer.append((state, pending_offset + state))
                else:
                    layer.append((sink, sink))
        else:
            for state in range(state_count):
                if state < 2 * memories:
                    universal = int(state >= pending_offset)
                    memory_state = state % memories
                    required = universal ^ (memory_state.bit_count() & 1)
                    next_memory = ((memory_state << 1) | universal) & mask
                    layer.append(
                        (
                            next_memory if required == 0 else sink,
                            next_memory if required == 1 else sink,
                        )
                    )
                else:
                    layer.append((sink, sink))
        transitions.append(layer)
    return branching_program_blueprint(
        seed=seed,
        case_id="c02",
        quantifiers=tuple(value for _ in range(pairs) for value in ("forall", "exists")),
        state_count=state_count,
        initial_state=0,
        transitions=transitions,
        accepting_states=set(range(memories)),
        family="memory_recurrence_response_game",
    )


def syndrome_game(seed: bytes, *, case_id: str, half: int, rank: int) -> TQBFBlueprint:
    stream = DeterministicStream(seed, case_id)
    state_count = 1 << rank
    columns = list(range(1, state_count))
    stream.shuffle(columns)
    universal_columns = [1 << index for index in range(rank)]
    while len(universal_columns) < half:
        candidate = columns[len(universal_columns) - rank]
        universal_columns.append(candidate)
    existential_columns = list(universal_columns)
    stream.shuffle(existential_columns)
    # Pairing is hidden only in the public circuit layout; equal column multisets make every
    # universal syndrome reachable by the existential block.
    all_columns = universal_columns + existential_columns
    transitions = [
        [(state, state ^ column) for state in range(state_count)] for column in all_columns
    ]
    return branching_program_blueprint(
        seed=seed,
        case_id=case_id,
        quantifiers=tuple(["forall"] * half + ["exists"] * half),
        state_count=state_count,
        initial_state=0,
        transitions=transitions,
        accepting_states={0},
        family=f"rank{rank}_affine_syndrome_game",
    )


def count_game(seed: bytes, *, half: int) -> TQBFBlueprint:
    state_count = 2 * half + 1
    offset = half
    transitions: list[list[tuple[int, int]]] = []
    for variable in range(2 * half):
        universal = variable < half
        layer: list[tuple[int, int]] = []
        for state in range(state_count):
            difference = state - offset
            changed = difference + (1 if universal else -1)
            changed = max(-half, min(half, changed))
            layer.append((state, changed + offset))
        transitions.append(layer)
    return branching_program_blueprint(
        seed=seed,
        case_id="c05",
        quantifiers=tuple(["forall"] * half + ["exists"] * half),
        state_count=state_count,
        initial_state=offset,
        transitions=transitions,
        accepting_states={offset},
        family="block_symmetric_count_game",
    )


def safety_game(seed: bytes, *, stages: int, states: int) -> TQBFBlueprint:
    stream = DeterministicStream(seed, "c04")
    terminal_winning = set(range(states // 2))
    # Build full three-bit action tables backwards while fixing a nontrivial winning half per layer.
    stage_tables: list[list[tuple[int, ...]]] = []
    winning = terminal_winning
    for _ in range(stages):
        table: list[tuple[int, ...]] = []
        previous_winning: set[int] = set()
        for state in range(states):
            actions: list[int] = []
            state_wins = state < states // 2
            if state_wins:
                previous_winning.add(state)
            for universal_action in range(4):
                good = list(winning)
                bad = [candidate for candidate in range(states) if candidate not in winning]
                stream.shuffle(good)
                stream.shuffle(bad)
                if state_wins:
                    pair = (good[0], bad[0]) if stream.randbelow(2) == 0 else (bad[0], good[0])
                elif universal_action == 0:
                    pair = (bad[0], bad[min(1, len(bad) - 1)])
                else:
                    pair = (good[0], bad[0])
                actions.extend(pair)
            table.append(tuple(actions))
        stage_tables.append(table)
        winning = previous_winning

    quantifiers = tuple(value for _ in range(stages) for value in ("forall", "forall", "exists"))
    transitions: list[list[tuple[int, int]]] = []
    # Expand each stage through two public action-prefix layers plus the existential repair layer.
    # The logical state includes action-prefix registers, so use the direct ITE expression compiler.
    builder = CircuitBuilder(len(quantifiers))
    accept = builder.const(1)
    reject = builder.const(0)
    layer_values = [accept if state in terminal_winning else reject for state in range(states)]
    for stage in range(stages - 1, -1, -1):
        variable_base = 3 * stage
        state_outputs: list[int] = []
        for state in range(states):
            leaves = [layer_values[target] for target in stage_tables[stage][state]]
            existential_nodes = [
                builder.ite(variable_base + 2, leaves[index], leaves[index + 1])
                for index in range(0, 8, 2)
            ]
            second_nodes = [
                builder.ite(
                    variable_base + 1,
                    existential_nodes[index],
                    existential_nodes[index + 1],
                )
                for index in range(0, 4, 2)
            ]
            state_outputs.append(builder.ite(variable_base, second_nodes[0], second_nodes[1]))
        layer_values = state_outputs
    del transitions
    output = add_semantic_padding(builder, layer_values[0], seed=seed, case_id="c04")
    return TQBFBlueprint(
        quantifiers=quantifiers,
        gates=tuple(builder.gates),
        output=output,
        family="layered_finite_state_safety_game",
    )


def _gf2_rank(rows: Sequence[int]) -> int:
    """Return the row rank of a small binary matrix encoded as bit masks."""

    pivots: dict[int, int] = {}
    for original in rows:
        row = original
        while row:
            pivot = row.bit_length() - 1
            if pivot not in pivots:
                pivots[pivot] = row
                break
            row ^= pivots[pivot]
    return len(pivots)


def _fixed_weight_full_rank_rows(
    stream: DeterministicStream,
    *,
    row_count: int,
    width: int,
    weight: int,
) -> tuple[int, ...]:
    """Sample fixed-weight rows until they have the requested full row rank."""

    if not 1 <= weight < width or not 1 <= row_count <= width:
        raise ValueError("invalid fixed-weight binary matrix dimensions")
    for _ in range(4_096):
        rows: list[int] = []
        for _row in range(row_count):
            columns = list(range(width))
            stream.shuffle(columns)
            mask = 0
            for column in columns[:weight]:
                mask |= 1 << column
            rows.append(mask)
        if _gf2_rank(rows) == row_count:
            return tuple(rows)
    raise ValueError("could not sample a full-rank fixed-weight binary matrix")


def _xor_via_ite(builder: CircuitBuilder, left: int, right: int) -> int:
    """Boolean XOR encoded without an ``xor`` gate.

    ITE(left, right, NOT(right)) is exactly left XOR right on the Boolean cube,
    and its prescribed field arithmetization is the usual XOR polynomial.
    """

    return builder.ite(left, right, builder.negate(right))


def dense_affine_components(
    seed: bytes,
    *,
    case_id: str,
    half: int,
    rank: int,
    row_weight: int,
) -> tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
    """Return the deterministic H, K and b used by a dense affine case."""

    stream = DeterministicStream(seed, case_id)
    universal_rows = _fixed_weight_full_rank_rows(
        stream,
        row_count=rank,
        width=half,
        weight=row_weight,
    )
    existential_rows = _fixed_weight_full_rank_rows(
        stream,
        row_count=rank,
        width=half,
        weight=row_weight,
    )
    right_hand_side = tuple(stream.randbelow(2) for _ in range(rank))
    return universal_rows, existential_rows, right_hand_side


def dense_affine_mix_order(seed: bytes, *, case_id: str, rank: int) -> tuple[int, ...]:
    """Return the seed-dependent triangular residual-mixing order."""

    stream = DeterministicStream(seed, case_id + "/residual-mix")
    order = list(range(rank))
    stream.shuffle(order)
    return tuple(order)


def dense_affine_relation_game(
    seed: bytes,
    *,
    case_id: str,
    half: int,
    rank: int,
    row_weight: int,
) -> TQBFBlueprint:
    """Build a high ordered-width true QBF with a low-rank spectral solver.

    The first block is universal, the second existential.  Two independently
    sampled full-row-rank matrices H and K define Hx + Ky = b.  Surjectivity of
    K makes the formula true, while full rank of H forces 2**rank distinct
    residual functions after the universal block.  A final asymmetric
    forall/exists wrapper makes the last two algebraic eliminations return the
    affine predicate *exactly*, rather than introducing a squared predicate.
    """

    if not 8 <= half <= 21:
        raise ValueError("half must be in [8, 21]")
    if not 3 <= rank <= min(21, half):
        raise ValueError("rank must be in [3, min(21, half)]")
    if not 2 <= row_weight < half:
        raise ValueError("row_weight must be in [2, half)")

    universal_rows, existential_rows, right_hand_side = dense_affine_components(
        seed,
        case_id=case_id,
        half=half,
        rank=rank,
        row_weight=row_weight,
    )
    stream = DeterministicStream(seed, case_id + "/wire-order")

    num_inputs = 2 * half + 2
    wrapper_universal = 2 * half
    wrapper_existential = wrapper_universal + 1
    builder = CircuitBuilder(num_inputs)
    residuals: list[int] = []
    for universal_mask, existential_mask, target in zip(
        universal_rows,
        existential_rows,
        right_hand_side,
        strict=True,
    ):
        selected = [column for column in range(half) if universal_mask & (1 << column)]
        selected.extend(half + column for column in range(half) if existential_mask & (1 << column))
        stream.shuffle(selected)
        parity = selected[0]
        for wire in selected[1:]:
            parity = _xor_via_ite(builder, parity, wire)

        target_wire = builder.const(target)
        disagreement = builder.ite(
            parity,
            target_wire,
            builder.negate(target_wire),
        )
        residuals.append(disagreement)

    mix_order = dense_affine_mix_order(seed, case_id=case_id, rank=rank)
    mixed_residuals = [residuals[mix_order[0]]]
    mixed_residuals.extend(
        _xor_via_ite(builder, residuals[current], residuals[previous])
        for previous, current in zip(mix_order[:-1], mix_order[1:], strict=True)
    )
    row_equalities = [builder.negate(residual) for residual in mixed_residuals]

    affine_predicate = builder.conjunction(row_equalities)
    one = builder.const(1)
    guarded_predicate = builder.ite(
        wrapper_universal,
        affine_predicate,
        one,
    )
    zero = builder.const(0)
    output = builder.ite(wrapper_existential, guarded_predicate, zero)
    output = add_semantic_padding(builder, output, seed=seed, case_id=case_id)
    return TQBFBlueprint(
        quantifiers=tuple(["forall"] * half + ["exists"] * half + ["forall", "exists"]),
        gates=tuple(builder.gates),
        output=output,
        family=f"rank{rank}_dense_affine_spectral_game",
    )


def blocked_reversible_relation_game(
    seed: bytes,
    *,
    case_id: str,
    large_block: int,
    small_block: int,
    quadratic_taps: int,
    row_cloak_rounds: int,
) -> TQBFBlueprint:
    """Build a unique-map relation with two hidden nonlinear factors.

    Each factor is a triangular reversible map.  Its public input and output
    coordinates are independently permuted, and every nontrivial output bit
    contains up to three quadratic taps from earlier triangular coordinates.
    The full map is therefore a bijection on 21 bits and has ordered residual
    width 2**21, while a maintainer who is told the factor boundary only needs
    tables for at most ``2 * large_block`` local variables.
    """

    if large_block + small_block != 21:
        raise ValueError("reversible block sizes must sum to 21")
    if not 8 <= small_block <= large_block <= 12:
        raise ValueError("reversible block sizes must lie in [8, 12]")
    if quadratic_taps not in (1, 2, 3):
        raise ValueError("quadratic_taps must be one, two, or three")
    if not 0 <= row_cloak_rounds <= 2:
        raise ValueError("row_cloak_rounds must lie in [0, 2]")

    half = large_block + small_block
    stream = DeterministicStream(seed, case_id + "/blocked-reversible")
    universal_coordinates = list(range(half))
    existential_coordinates = list(range(half, 2 * half))
    stream.shuffle(universal_coordinates)
    stream.shuffle(existential_coordinates)
    builder = CircuitBuilder(2 * half + 2)
    row_equalities: list[int] = []
    offset = 0
    for block_size in (large_block, small_block):
        inputs = universal_coordinates[offset : offset + block_size]
        outputs = existential_coordinates[offset : offset + block_size]
        offset += block_size
        stream.shuffle(inputs)
        stream.shuffle(outputs)
        for position, (target, output_variable) in enumerate(zip(inputs, outputs, strict=True)):
            state = builder.negate(target)
            if position == 1:
                state = _xor_via_ite(builder, state, inputs[0])
            elif position >= 2:
                product = builder.binary("and", inputs[position - 1], inputs[position - 2])
                state = _xor_via_ite(builder, state, product)
                if quadratic_taps >= 2 and position >= 4:
                    second_product = builder.binary(
                        "and", inputs[position - 3], inputs[position - 4]
                    )
                    state = _xor_via_ite(builder, state, second_product)
                if quadratic_taps >= 3 and position >= 6:
                    third_product = builder.binary(
                        "and", inputs[position - 5], inputs[position - 6]
                    )
                    state = _xor_via_ite(builder, state, third_product)
            residual = _xor_via_ite(builder, output_variable, state)
            equality = builder.negate(residual)
            # C06 uses reachable, field-exact identity cloaks around individual
            # rows.  These gates make the public syntax materially different
            # without changing the polynomial, its degree schedule, or the
            # local tables needed by the hinted reference prover.
            for _ in range(row_cloak_rounds):
                cloak = stream.randbelow(4)
                if cloak == 0:
                    equality = builder.negate(builder.negate(equality))
                elif cloak == 1:
                    equality = builder.binary("and", equality, builder.const(1))
                elif cloak == 2:
                    equality = builder.binary("or", equality, builder.const(0))
                else:
                    constant = builder.const(stream.randbelow(2))
                    equality = builder.ite(constant, equality, equality)
            row_equalities.append(equality)

    stream.shuffle(row_equalities)
    if row_cloak_rounds:
        # Preserve the cloaked row boundaries: ITE(a, 0, b) is exactly a*b
        # under both Boolean and prescribed field semantics, but cannot be
        # mistaken for the balanced conjunction tree by a syntax-only parser.
        zero_for_tree = builder.const(0)
        work = list(row_equalities)
        while len(work) > 1:
            next_work: list[int] = []
            for index in range(0, len(work), 2):
                if index + 1 == len(work):
                    next_work.append(work[index])
                else:
                    next_work.append(builder.ite(work[index], zero_for_tree, work[index + 1]))
            work = next_work
        reversible_predicate = work[0]
    else:
        reversible_predicate = builder.conjunction(row_equalities)
    wrapper_universal = 2 * half
    wrapper_existential = wrapper_universal + 1
    one = builder.const(1)
    guarded_predicate = builder.ite(
        wrapper_universal,
        reversible_predicate,
        one,
    )
    zero = builder.const(0)
    output = builder.ite(wrapper_existential, guarded_predicate, zero)
    output = add_semantic_padding(builder, output, seed=seed, case_id=case_id)
    return TQBFBlueprint(
        quantifiers=tuple(["forall"] * half + ["exists"] * half + ["forall", "exists"]),
        gates=tuple(builder.gates),
        output=output,
        family=(
            f"blocked_reversible_{large_block}_{small_block}_q{quadratic_taps}"
            f"_cloak{row_cloak_rounds}"
        ),
    )


CASE_DEFAULTS: Final[Mapping[str, Mapping[str, object]]] = {
    "c01": {"pairs": 9},
    "c02": {"pairs": 12, "memory": 5},
    "c03": {"half": 12, "rank": 5},
    "c04": {
        "large_block": 11,
        "small_block": 10,
        "quadratic_taps": 1,
        "row_cloak_rounds": 0,
    },
    "c05": {
        "large_block": 12,
        "small_block": 9,
        "quadratic_taps": 2,
        "row_cloak_rounds": 0,
    },
    "c06": {
        "large_block": 12,
        "small_block": 9,
        "quadratic_taps": 2,
        "row_cloak_rounds": 1,
    },
}


def build_case(case_id: str, seed: bytes, parameters: Mapping[str, object]) -> TQBFBlueprint:
    if case_id == "c01":
        return width_four_response_game(
            seed, pairs=integer_parameter(parameters, "pairs", minimum=2, maximum=12)
        )
    if case_id == "c02":
        return recurrence_game(
            seed,
            pairs=integer_parameter(parameters, "pairs", minimum=4, maximum=12),
            memory=integer_parameter(parameters, "memory", minimum=2, maximum=6),
        )
    if case_id == "c03":
        return syndrome_game(
            seed,
            case_id=case_id,
            half=integer_parameter(parameters, "half", minimum=8, maximum=14),
            rank=integer_parameter(parameters, "rank", minimum=3, maximum=7),
        )
    if case_id in {"c04", "c05", "c06"}:
        return blocked_reversible_relation_game(
            seed,
            case_id=case_id,
            large_block=integer_parameter(parameters, "large_block", minimum=8, maximum=12),
            small_block=integer_parameter(parameters, "small_block", minimum=8, maximum=12),
            quadratic_taps=integer_parameter(parameters, "quadratic_taps", minimum=1, maximum=3),
            row_cloak_rounds=integer_parameter(
                parameters, "row_cloak_rounds", minimum=0, maximum=2
            ),
        )
    raise ValueError(f"unsupported new TQBF case: {case_id}")


__all__ = ["CASE_DEFAULTS", "build_case"]
