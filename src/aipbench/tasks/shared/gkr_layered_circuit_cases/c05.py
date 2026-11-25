"""Shared primitives used by the current Merlin-Bench tasks."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .common import (
    MODULUS,
    CircuitBlueprint,
    DeterministicStream,
    add_gate,
    copy_gate,
    mul_gate,
    padded_stage,
    padded_values,
    random_nonzero_values,
    require_integer,
    sub_gate,
    sum_reduction,
)


def _schedule(records: int) -> list[list[tuple[int, int, bool]]]:
    stages: list[list[tuple[int, int, bool]]] = []
    size = 2
    while size <= records:
        stride = size // 2
        while stride:
            stage: list[tuple[int, int, bool]] = []
            for first in range(records):
                second = first ^ stride
                if second > first:
                    stage.append((first, second, (first & size) == 0))
            stages.append(stage)
            stride //= 2
        size *= 2
    return stages


def build(stream: DeterministicStream, parameters: Mapping[str, Any]) -> CircuitBlueprint:
    records = require_integer(parameters, "records", minimum=2, maximum=16)
    fields = require_integer(parameters, "payload_fields", minimum=1, maximum=8)
    if records & (records - 1):
        raise ValueError("records must be a power of two")
    record_width = fields + 1
    keys = [stream.integer(2) for _ in range(records)]
    payloads = random_nonzero_values(stream, records * fields)
    logical: list[int] = []
    for record in range(records):
        logical.append(keys[record])
        logical.extend(payloads[record * fields : (record + 1) * fields])
    inputs = padded_values(logical)
    child_width = len(inputs)
    layers: list[tuple[Any, ...]] = []

    for comparator_stage in _schedule(records):
        # Carry all records and calculate a*b.
        gates: list[Any] = [copy_gate(index) for index in range(records * record_width)]
        for first, second, _ in comparator_stage:
            gates.append(mul_gate(first * record_width, second * record_width))
        stage = padded_stage(gates, child_width)
        layers.append(stage)
        ab_base = records * record_width

        # Carry records and calculate the direction-specific swap bit.
        gates = [copy_gate(index) for index in range(records * record_width)]
        for pair_index, (first, second, ascending) in enumerate(comparator_stage):
            selected = first if ascending else second
            gates.append(sub_gate(selected * record_width, ab_base + pair_index))
        stage = padded_stage(gates, len(stage))
        layers.append(stage)
        swap_base = records * record_width

        # Carry records and swap bits; calculate both payload differences.
        gates = [copy_gate(index) for index in range(records * record_width)]
        gates.extend(copy_gate(swap_base + index) for index in range(len(comparator_stage)))
        for first, second, _ in comparator_stage:
            for field in range(1, record_width):
                gates.append(sub_gate(second * record_width + field, first * record_width + field))
                gates.append(sub_gate(first * record_width + field, second * record_width + field))
        stage = padded_stage(gates, len(stage))
        layers.append(stage)
        difference_base = records * record_width + len(comparator_stage)

        # Carry records and swaps; multiply every difference by its swap bit.
        gates = [copy_gate(index) for index in range(records * record_width)]
        gates.extend(copy_gate(swap_base + index) for index in range(len(comparator_stage)))
        difference_index = difference_base
        for pair_index, _pair in enumerate(comparator_stage):
            for _field in range(1, record_width):
                gates.append(mul_gate(swap_base + pair_index, difference_index))
                gates.append(mul_gate(swap_base + pair_index, difference_index + 1))
                difference_index += 2
        stage = padded_stage(gates, len(stage))
        layers.append(stage)
        delta_base = records * record_width + len(comparator_stage)

        # Produce exactly the next record table.
        output: list[Any] = [copy_gate(index) for index in range(records * record_width)]
        delta_index = delta_base
        for pair_index, (first, second, ascending) in enumerate(comparator_stage):
            swap = records * record_width + pair_index
            if ascending:
                output[first * record_width] = sub_gate(first * record_width, swap)
                output[second * record_width] = add_gate(second * record_width, swap)
            else:
                output[first * record_width] = add_gate(first * record_width, swap)
                output[second * record_width] = sub_gate(second * record_width, swap)
            for field in range(1, record_width):
                output[first * record_width + field] = add_gate(
                    first * record_width + field, delta_index
                )
                output[second * record_width + field] = add_gate(
                    second * record_width + field, delta_index + 1
                )
                delta_index += 2
        stage = padded_stage(output, len(stage))
        layers.append(stage)
        child_width = len(stage)

    weights = random_nonzero_values(stream, records * record_width)
    weighted = [copy_gate(index, weights[index]) for index in range(records * record_width)]
    stage = padded_stage(weighted, child_width)
    layers.append(stage)
    layers.extend(sum_reduction(len(stage)))

    records_data = [
        [keys[index], *payloads[index * fields : (index + 1) * fields]] for index in range(records)
    ]
    for comparator_stage in _schedule(records):
        for first, second, ascending in comparator_stage:
            inversion = (
                records_data[first][0] > records_data[second][0]
                if ascending
                else records_data[first][0] < records_data[second][0]
            )
            if inversion:
                records_data[first], records_data[second] = (
                    records_data[second],
                    records_data[first],
                )
    flattened = [value for record in records_data for value in record]
    result = sum(value * weight for value, weight in zip(flattened, weights, strict=True))
    return CircuitBlueprint(inputs, tuple(layers), result % MODULUS)
