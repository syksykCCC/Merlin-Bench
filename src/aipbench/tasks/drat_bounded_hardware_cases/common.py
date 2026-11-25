"""A small deterministic AIG builder and bounded Tseitin compiler."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Final


class DeterministicStream:
    """Hardware-task-specific SHA-256 stream."""

    _DOMAIN: Final = b"aipbench/t3-drat-bounded-hardware/cases/v1\x00"

    def __init__(self, seed: bytes) -> None:
        self._seed = bytes(seed)
        self._counter = 0

    def randbelow(self, bound: int) -> int:
        if bound <= 0:
            raise ValueError("bound must be positive")
        while True:
            digest = hashlib.sha256(
                self._DOMAIN + self._seed + self._counter.to_bytes(8, "big")
            ).digest()
            self._counter += 1
            value = int.from_bytes(digest, "big")
            limit = (1 << 256) - ((1 << 256) % bound)
            if value < limit:
                return value % bound


@dataclass(frozen=True)
class Latch:
    literal: int
    next_literal: int
    initial: int
    name: str


@dataclass(frozen=True)
class HardwareBlueprint:
    title: str
    circuit_name: str
    horizon: int
    aiger_aag: str
    bound_cnf: str
    num_cnf_variables: int
    num_cnf_clauses: int
    public_features: dict[str, int | str]


class AigBuilder:
    """Build one-output sequential ASCII AIGER circuits."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._next_variable = 1
        self.inputs: list[tuple[int, str]] = []
        self._latch_slots: list[tuple[int, int | None, int, str]] = []
        self.ands: list[tuple[int, int, int]] = []
        self._and_cache: dict[tuple[int, int], int] = {}
        self.bad_literal = 0

    @property
    def max_variable(self) -> int:
        return self._next_variable - 1

    def _fresh_literal(self) -> int:
        literal = 2 * self._next_variable
        self._next_variable += 1
        return literal

    def input(self, name: str) -> int:
        literal = self._fresh_literal()
        self.inputs.append((literal, name))
        return literal

    def latch(self, name: str, *, initial: int = 0) -> int:
        if initial not in (0, 1):
            raise ValueError("AIGER latch initial value must be zero or one")
        literal = self._fresh_literal()
        self._latch_slots.append((literal, None, initial, name))
        return literal

    def set_next(self, latch_literal: int, next_literal: int) -> None:
        for index, (literal, current_next, initial, name) in enumerate(self._latch_slots):
            if literal != latch_literal:
                continue
            if current_next is not None:
                raise ValueError("latch next-state assigned twice")
            self._latch_slots[index] = (literal, next_literal, initial, name)
            return
        raise ValueError("unknown latch literal")

    @staticmethod
    def neg(literal: int) -> int:
        return literal ^ 1

    def and_(self, left: int, right: int) -> int:
        if left == 0 or right == 0 or left == (right ^ 1):
            return 0
        if left == 1:
            return right
        if right == 1 or left == right:
            return left
        left, right = sorted((left, right))
        key = (left, right)
        cached = self._and_cache.get(key)
        if cached is not None:
            return cached
        output = self._fresh_literal()
        self.ands.append((output, left, right))
        self._and_cache[key] = output
        return output

    def or_(self, left: int, right: int) -> int:
        return self.neg(self.and_(self.neg(left), self.neg(right)))

    def xor(self, left: int, right: int) -> int:
        return self.or_(self.and_(left, self.neg(right)), self.and_(self.neg(left), right))

    def mux(self, select: int, when_true: int, when_false: int) -> int:
        return self.or_(self.and_(select, when_true), self.and_(self.neg(select), when_false))

    def any_(self, literals: list[int]) -> int:
        result = 0
        for literal in literals:
            result = self.or_(result, literal)
        return result

    def all_(self, literals: list[int]) -> int:
        result = 1
        for literal in literals:
            result = self.and_(result, literal)
        return result

    def latches(self) -> tuple[Latch, ...]:
        result: list[Latch] = []
        for literal, next_literal, initial, name in self._latch_slots:
            if next_literal is None:
                raise ValueError(f"latch {name} has no next-state expression")
            result.append(Latch(literal, next_literal, initial, name))
        return tuple(result)

    def render_aag(self) -> str:
        latches = self.latches()
        lines = [f"aag {self.max_variable} {len(self.inputs)} {len(latches)} 1 {len(self.ands)}"]
        lines.extend(str(literal) for literal, _name in self.inputs)
        lines.extend(f"{latch.literal} {latch.next_literal} {latch.initial}" for latch in latches)
        lines.append(str(self.bad_literal))
        lines.extend(f"{output} {left} {right}" for output, left, right in self.ands)
        lines.extend(f"i{index} {name}" for index, (_literal, name) in enumerate(self.inputs))
        lines.extend(f"l{index} {latch.name}" for index, latch in enumerate(latches))
        lines.append("o0 bad")
        lines.extend(("c", f"AIPBench bounded hardware circuit: {self.name}"))
        return "\n".join(lines) + "\n"


def _cnf_literal(aig_literal: int, frame: int, max_variable: int) -> int | bool:
    if aig_literal == 0:
        return False
    if aig_literal == 1:
        return True
    variable = frame * max_variable + aig_literal // 2
    return -variable if aig_literal & 1 else variable


def _append_clause(clauses: list[list[int]], values: list[int | bool]) -> None:
    if any(value is True for value in values):
        return
    integers = [int(value) for value in values if value is not False]
    if any(-value in integers for value in integers):
        return
    clauses.append(list(dict.fromkeys(integers)))


def compile_bounded_cnf(builder: AigBuilder, horizon: int) -> tuple[str, int, int]:
    """Compile Init/Trans/Bad<=H to DIMACS with a fixed Tseitin encoding."""

    if horizon <= 0:
        raise ValueError("horizon must be positive")
    maximum = builder.max_variable
    latches = builder.latches()
    clauses: list[list[int]] = []
    for latch in latches:
        initial_literal = _cnf_literal(latch.literal, 0, maximum)
        assert isinstance(initial_literal, int)
        _append_clause(clauses, [initial_literal if latch.initial else -initial_literal])
    for frame in range(horizon + 1):
        for output, left, right in builder.ands:
            z = _cnf_literal(output, frame, maximum)
            a = _cnf_literal(left, frame, maximum)
            b = _cnf_literal(right, frame, maximum)
            assert isinstance(z, int)
            _append_clause(clauses, [-z, a])
            _append_clause(clauses, [-z, b])
            neg_a = not a if isinstance(a, bool) else -a
            neg_b = not b if isinstance(b, bool) else -b
            _append_clause(clauses, [z, neg_a, neg_b])
        if frame == horizon:
            continue
        for latch in latches:
            following = _cnf_literal(latch.literal, frame + 1, maximum)
            expression = _cnf_literal(latch.next_literal, frame, maximum)
            assert isinstance(following, int)
            _append_clause(clauses, [-following, expression])
            neg_expression = not expression if isinstance(expression, bool) else -expression
            _append_clause(clauses, [following, neg_expression])
    bad_frames = [_cnf_literal(builder.bad_literal, frame, maximum) for frame in range(horizon + 1)]
    _append_clause(clauses, bad_frames)
    num_variables = (horizon + 1) * maximum
    header = [
        "c AIPBench fixed sequential-AIG Tseitin unrolling v1",
        f"c source {builder.name}",
        f"c horizon {horizon}",
        f"p cnf {num_variables} {len(clauses)}",
    ]
    body = [" ".join(str(value) for value in clause) + " 0" for clause in clauses]
    return "\n".join((*header, *body, "")), num_variables, len(clauses)


def _update_unary_fifo(builder: AigBuilder, depth: int) -> tuple[list[int], int, int]:
    push = builder.input("push")
    pop = builder.input("pop")
    occupied = [builder.latch(f"occupied_{index}") for index in range(depth)]
    empty = builder.neg(occupied[0])
    full = occupied[-1]
    push_only = builder.all_([push, builder.neg(pop), builder.neg(full)])
    pop_only = builder.all_([pop, builder.neg(push), builder.neg(empty)])
    for index, latch in enumerate(occupied):
        pushed = 1 if index == 0 else occupied[index - 1]
        popped = 0 if index + 1 == depth else occupied[index + 1]
        next_literal = builder.mux(push_only, pushed, builder.mux(pop_only, popped, latch))
        builder.set_next(latch, next_literal)
    return occupied, push, pop


def build_fifo_prefix(depth: int, horizon: int) -> AigBuilder:
    builder = AigBuilder("fifo-prefix-safety")
    occupied, _push, _pop = _update_unary_fifo(builder, depth)
    builder.bad_literal = builder.any_(
        [
            builder.and_(occupied[index + 1], builder.neg(occupied[index]))
            for index in range(depth - 1)
        ]
    )
    return builder


def build_fifo_underflow(depth: int, horizon: int) -> AigBuilder:
    del horizon
    builder = AigBuilder("fifo-underflow-safety")
    occupied, _push, pop = _update_unary_fifo(builder, depth)
    pop_fire = builder.and_(pop, occupied[0])
    builder.bad_literal = builder.and_(pop_fire, builder.neg(occupied[0]))
    return builder


def _round_robin(builder: AigBuilder, agents: int) -> tuple[list[int], list[int]]:
    requests = [builder.input(f"request_{index}") for index in range(agents)]
    token = [builder.latch(f"token_{index}", initial=int(index == 0)) for index in range(agents)]
    for index, latch in enumerate(token):
        builder.set_next(latch, token[(index - 1) % agents])
    grants = [builder.and_(requests[index], token[index]) for index in range(agents)]
    return token, grants


def build_arbiter_mutex(agents: int, horizon: int) -> AigBuilder:
    del horizon
    builder = AigBuilder("round-robin-mutual-exclusion")
    requests = [builder.input(f"request_{index}") for index in range(agents)]
    advance = builder.input("advance")
    token = [builder.latch(f"token_{index}", initial=int(index == 0)) for index in range(agents)]
    for index, latch in enumerate(token):
        rotated = token[(index - 1) % agents]
        builder.set_next(latch, builder.mux(advance, rotated, latch))
    grants = [builder.and_(requests[index], token[index]) for index in range(agents)]
    collisions = [
        builder.and_(grants[left], grants[right])
        for left in range(agents)
        for right in range(left + 1, agents)
    ]
    builder.bad_literal = builder.any_(collisions)
    return builder


def build_arbiter_fairness(agents: int, horizon: int) -> AigBuilder:
    del horizon
    builder = AigBuilder("round-robin-bounded-fairness")
    requests = [builder.input(f"request_{index}") for index in range(agents)]
    advance = builder.input("advance")
    token = [builder.latch(f"token_{index}", initial=int(index == 0)) for index in range(agents)]
    for index, latch in enumerate(token):
        rotated = token[(index - 1) % agents]
        builder.set_next(latch, builder.mux(advance, rotated, latch))
    grants = [builder.and_(requests[index], token[index]) for index in range(agents)]
    waiting = [builder.latch(f"wait_{index}") for index in range(agents)]
    condition = builder.and_(builder.and_(requests[0], advance), builder.neg(grants[0]))
    for index, latch in enumerate(waiting):
        predecessor = 1 if index == 0 else waiting[index - 1]
        builder.set_next(latch, builder.and_(condition, predecessor))
    builder.bad_literal = builder.and_(condition, waiting[-1])
    return builder


def _credit_state(builder: AigBuilder, capacity: int) -> tuple[list[int], list[int], int]:
    send = builder.input("send")
    returned = builder.input("credit_return")
    credit = [builder.latch(f"credit_{index}", initial=1) for index in range(capacity)]
    flight = [builder.latch(f"flight_{index}") for index in range(capacity)]
    can_send = builder.and_(send, credit[0])
    can_return = builder.and_(returned, flight[0])
    send_only = builder.and_(can_send, builder.neg(can_return))
    return_only = builder.and_(can_return, builder.neg(can_send))
    for index in range(capacity):
        less_credit = 0 if index + 1 == capacity else credit[index + 1]
        more_credit = 1 if index == 0 else credit[index - 1]
        less_flight = 0 if index + 1 == capacity else flight[index + 1]
        more_flight = 1 if index == 0 else flight[index - 1]
        builder.set_next(
            credit[index],
            builder.mux(
                send_only, less_credit, builder.mux(return_only, more_credit, credit[index])
            ),
        )
        builder.set_next(
            flight[index],
            builder.mux(
                send_only, more_flight, builder.mux(return_only, less_flight, flight[index])
            ),
        )
    return credit, flight, can_send


def build_credit_conservation(capacity: int, horizon: int) -> AigBuilder:
    del horizon
    builder = AigBuilder("credit-router-conservation")
    credit, flight, _forward = _credit_state(builder, capacity)
    builder.bad_literal = builder.any_(
        [
            builder.xor(credit[index], builder.neg(flight[capacity - 1 - index]))
            for index in range(capacity)
        ]
    )
    return builder


def build_credit_forwarding(capacity: int, horizon: int) -> AigBuilder:
    del horizon
    builder = AigBuilder("credit-router-forwarding-guard")
    send = builder.input("send")
    returned = builder.input("credit_return")

    def tracker(prefix: str) -> tuple[list[int], list[int], int]:
        credit = [builder.latch(f"{prefix}_credit_{index}", initial=1) for index in range(capacity)]
        flight = [builder.latch(f"{prefix}_flight_{index}") for index in range(capacity)]
        can_send = builder.and_(send, credit[0])
        can_return = builder.and_(returned, flight[0])
        send_only = builder.and_(can_send, builder.neg(can_return))
        return_only = builder.and_(can_return, builder.neg(can_send))
        for index in range(capacity):
            less_credit = 0 if index + 1 == capacity else credit[index + 1]
            more_credit = 1 if index == 0 else credit[index - 1]
            less_flight = 0 if index + 1 == capacity else flight[index + 1]
            more_flight = 1 if index == 0 else flight[index - 1]
            builder.set_next(
                credit[index],
                builder.mux(
                    send_only,
                    less_credit,
                    builder.mux(return_only, more_credit, credit[index]),
                ),
            )
            builder.set_next(
                flight[index],
                builder.mux(
                    send_only,
                    more_flight,
                    builder.mux(return_only, less_flight, flight[index]),
                ),
            )
        return credit, flight, can_send

    credit, _flight, _actual_forward = tracker("actual")
    shadow_credit, _shadow_flight, shadow_forward = tracker("shadow")
    builder.bad_literal = builder.and_(shadow_forward, builder.neg(credit[0]))
    return builder


def build_pipeline_flush(stages: int, horizon: int) -> AigBuilder:
    del horizon
    builder = AigBuilder("pipeline-flush-stall-safety")
    issue = builder.input("issue")
    stall = builder.input("stall")
    flush = builder.input("flush")
    valid = [builder.latch(f"valid_{index}") for index in range(stages)]
    pending_flush = builder.latch("pending_flush")
    progress = [builder.latch(f"flush_progress_{index}") for index in range(stages)]
    active = builder.or_(pending_flush, flush)
    advance = builder.and_(active, builder.neg(stall))
    complete = progress[-1]
    builder.set_next(
        pending_flush,
        builder.mux(flush, 1, builder.mux(complete, 0, pending_flush)),
    )
    for index, latch in enumerate(valid):
        shifted = builder.and_(issue, builder.neg(active)) if index == 0 else valid[index - 1]
        builder.set_next(latch, builder.mux(stall, latch, shifted))
    for index, latch in enumerate(progress):
        shifted = 1 if index == 0 else progress[index - 1]
        builder.set_next(
            latch,
            builder.mux(
                flush,
                builder.mux(stall, 0, int(index == 0)),
                builder.mux(advance, shifted, builder.mux(pending_flush, latch, 0)),
            ),
        )
    builder.bad_literal = builder.and_(complete, builder.any_(valid))
    return builder


def build_pipeline_writeback(stages: int, horizon: int) -> AigBuilder:
    del horizon
    builder = AigBuilder("pipeline-writeback-consistency")
    issue = builder.input("issue")
    input_tag = builder.input("input_tag")
    stall = builder.input("stall")
    flush = builder.input("flush")
    valid = [builder.latch(f"valid_{index}") for index in range(stages)]
    tag = [builder.latch(f"tag_{index}") for index in range(stages)]
    shadow = [builder.latch(f"shadow_{index}") for index in range(stages)]
    for index in range(stages):
        shifted_valid = issue if index == 0 else valid[index - 1]
        shifted_tag = input_tag if index == 0 else tag[index - 1]
        shifted_shadow = input_tag if index == 0 else shadow[index - 1]
        builder.set_next(
            valid[index], builder.mux(flush, 0, builder.mux(stall, valid[index], shifted_valid))
        )
        builder.set_next(
            tag[index], builder.mux(flush, 0, builder.mux(stall, tag[index], shifted_tag))
        )
        builder.set_next(
            shadow[index],
            builder.mux(flush, 0, builder.mux(stall, shadow[index], shifted_shadow)),
        )
    builder.bad_literal = builder.and_(valid[-1], builder.xor(tag[-1], shadow[-1]))
    return builder


def finish_blueprint(
    *,
    title: str,
    builder: AigBuilder,
    horizon: int,
    features: dict[str, int | str],
) -> HardwareBlueprint:
    cnf, variables, clauses = compile_bounded_cnf(builder, horizon)
    return HardwareBlueprint(
        title=title,
        circuit_name=builder.name,
        horizon=horizon,
        aiger_aag=builder.render_aag(),
        bound_cnf=cnf,
        num_cnf_variables=variables,
        num_cnf_clauses=clauses,
        public_features=features,
    )


DEFAULT_CASE_DOMAIN: Final = b"aipbench/t3-drat-hardware/cases/v1\x00"


__all__ = [
    "AigBuilder",
    "DEFAULT_CASE_DOMAIN",
    "DeterministicStream",
    "HardwareBlueprint",
    "build_arbiter_fairness",
    "build_arbiter_mutex",
    "build_credit_conservation",
    "build_credit_forwarding",
    "build_fifo_prefix",
    "build_fifo_underflow",
    "build_pipeline_flush",
    "build_pipeline_writeback",
    "compile_bounded_cnf",
    "finish_blueprint",
]
