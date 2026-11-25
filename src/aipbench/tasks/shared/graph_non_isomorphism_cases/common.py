"""Shared primitives used by the current Merlin-Bench tasks."""

from __future__ import annotations

import hashlib
from collections import Counter, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from math import isqrt
from typing import Any, Final


class DeterministicStream:
    """Domain-separated SHA-256 stream used only for deterministic generation."""

    _DOMAIN: Final = b"aipbench/graph-non-isomorphism/generator/v1\x00"

    def __init__(self, seed: bytes) -> None:
        self._seed = bytes(seed)
        self._counter = 0
        self._buffer = bytearray()

    def _refill(self) -> None:
        self._buffer.extend(
            hashlib.sha256(
                self._DOMAIN
                + len(self._seed).to_bytes(8, "big")
                + self._seed
                + self._counter.to_bytes(16, "big")
            ).digest()
        )
        self._counter += 1

    def take(self, length: int) -> bytes:
        if length < 0:
            raise ValueError("length must be non-negative")
        while len(self._buffer) < length:
            self._refill()
        result = bytes(self._buffer[:length])
        del self._buffer[:length]
        return result

    def randbelow(self, upper_exclusive: int) -> int:
        if upper_exclusive <= 0:
            raise ValueError("upper_exclusive must be positive")
        width = max(1, (upper_exclusive.bit_length() + 7) // 8)
        sample_space = 1 << (8 * width)
        rejection_limit = sample_space - sample_space % upper_exclusive
        while True:
            candidate = int.from_bytes(self.take(width), "big")
            if candidate < rejection_limit:
                return candidate % upper_exclusive

    def shuffle(self, values: list[Any]) -> None:
        for index in range(len(values) - 1, 0, -1):
            swap_index = self.randbelow(index + 1)
            values[index], values[swap_index] = values[swap_index], values[index]


def normalized_edges(pairs: set[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    """Return a canonical simple-edge tuple and reject loops."""

    normalized: set[tuple[int, int]] = set()
    for first, second in pairs:
        if first == second:
            raise ValueError("a logical graph cannot contain a loop")
        normalized.add((min(first, second), max(first, second)))
    return tuple(sorted(normalized))


@dataclass(frozen=True)
class LogicalGraph:
    """A canonically serialized, zero-indexed, vertex-coloured simple graph."""

    num_vertices: int
    colors: tuple[int, ...]
    edges: tuple[tuple[int, int], ...]


def shrikhande_graph() -> LogicalGraph:
    differences = {(1, 0), (3, 0), (0, 1), (0, 3), (1, 1), (3, 3)}
    edges: set[tuple[int, int]] = set()
    for first_x in range(4):
        for first_y in range(4):
            first = 4 * first_x + first_y
            for dx, dy in differences:
                second = 4 * ((first_x + dx) % 4) + (first_y + dy) % 4
                if first != second:
                    edges.add((min(first, second), max(first, second)))
    return LogicalGraph(16, (0,) * 16, tuple(sorted(edges)))


def rook_graph() -> LogicalGraph:
    edges = {
        (4 * first_row + first_column, 4 * second_row + second_column)
        for first_row in range(4)
        for first_column in range(4)
        for second_row in range(4)
        for second_column in range(4)
        if (first_row, first_column) < (second_row, second_column)
        and (first_row == second_row or first_column == second_column)
    }
    return LogicalGraph(16, (0,) * 16, tuple(sorted(edges)))


def line_graph(root: LogicalGraph) -> LogicalGraph:
    _validate_logical_graph(root)
    incident: list[list[int]] = [[] for _ in range(root.num_vertices)]
    for edge_id, (first, second) in enumerate(root.edges):
        incident[first].append(edge_id)
        incident[second].append(edge_id)
    edges: set[tuple[int, int]] = set()
    for edge_ids in incident:
        for left_index, first in enumerate(edge_ids):
            for second in edge_ids[left_index + 1 :]:
                edges.add((min(first, second), max(first, second)))
    return LogicalGraph(len(root.edges), (0,) * len(root.edges), tuple(sorted(edges)))


@dataclass(frozen=True)
class PairBlueprint:
    """Two logical non-isomorphic graphs before public label hiding."""

    graph0: LogicalGraph
    graph1: LogicalGraph
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FinalizedCase:
    public_instance: Mapping[str, Any]
    private_instance: Mapping[str, Any]
    generation_metadata: Mapping[str, Any]


def _strict_int(value: object, *, description: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{description} must be an integer >= {minimum}")
    return value


def parse_public_graph(graph_obj: object) -> LogicalGraph:
    """Strictly parse one public graph, including canonical edge-array ordering."""

    if not isinstance(graph_obj, Mapping):
        raise ValueError("graph must be an object")
    if set(graph_obj) != {"num_vertices", "colors", "edges"}:
        raise ValueError("graph must contain exactly num_vertices, colors, and edges")
    num_vertices = _strict_int(graph_obj["num_vertices"], description="num_vertices", minimum=1)
    raw_colors = graph_obj["colors"]
    if not isinstance(raw_colors, list) or len(raw_colors) != num_vertices:
        raise ValueError("colors must be an array of length num_vertices")
    colors = tuple(_strict_int(color, description="every color", minimum=0) for color in raw_colors)
    raw_edges = graph_obj["edges"]
    if not isinstance(raw_edges, list):
        raise ValueError("edges must be an array")
    edges: list[tuple[int, int]] = []
    previous: tuple[int, int] | None = None
    for raw_edge in raw_edges:
        if not isinstance(raw_edge, list) or len(raw_edge) != 2:
            raise ValueError("every edge must be a two-element array")
        first = _strict_int(raw_edge[0], description="edge endpoint", minimum=0)
        second = _strict_int(raw_edge[1], description="edge endpoint", minimum=0)
        edge = (first, second)
        if not 0 <= first < second < num_vertices:
            raise ValueError("every edge must satisfy 0 <= u < v < num_vertices")
        if previous is not None and edge <= previous:
            raise ValueError("edge array must be strictly lexicographically sorted")
        previous = edge
        edges.append(edge)
    return LogicalGraph(num_vertices=num_vertices, colors=colors, edges=tuple(edges))


def _validate_logical_graph(graph: LogicalGraph) -> None:
    if isinstance(graph.num_vertices, bool) or graph.num_vertices < 1:
        raise ValueError("logical graph must contain at least one vertex")
    if len(graph.colors) != graph.num_vertices or any(
        isinstance(color, bool) or not isinstance(color, int) or color < 0 for color in graph.colors
    ):
        raise ValueError("logical graph has an invalid color vector")
    previous: tuple[int, int] | None = None
    for edge in graph.edges:
        if (
            not isinstance(edge, tuple)
            or len(edge) != 2
            or isinstance(edge[0], bool)
            or isinstance(edge[1], bool)
            or not isinstance(edge[0], int)
            or not isinstance(edge[1], int)
        ):
            raise ValueError("logical graph contains a malformed edge")
        if not 0 <= edge[0] < edge[1] < graph.num_vertices:
            raise ValueError("logical graph edge is not normalized")
        if previous is not None and edge <= previous:
            raise ValueError("logical graph edges are not strictly sorted and unique")
        previous = edge


def serialize_graph(graph: LogicalGraph) -> dict[str, Any]:
    _validate_logical_graph(graph)
    return {
        "num_vertices": graph.num_vertices,
        "colors": list(graph.colors),
        "edges": [[first, second] for first, second in graph.edges],
    }


def relabel_graph(graph: LogicalGraph, permutation: Sequence[int]) -> LogicalGraph:
    """Apply ``permutation[old_vertex] = new_vertex`` and serialize canonically."""

    _validate_logical_graph(graph)
    if len(permutation) != graph.num_vertices or any(
        isinstance(vertex, bool) or not isinstance(vertex, int) for vertex in permutation
    ):
        raise ValueError("permutation must contain exactly num_vertices strict integers")
    if set(permutation) != set(range(graph.num_vertices)):
        raise ValueError("permutation must be a bijection of the vertex set")
    colors = [0] * graph.num_vertices
    for old_vertex, new_vertex in enumerate(permutation):
        colors[new_vertex] = graph.colors[old_vertex]
    edges = normalized_edges(
        {(permutation[first], permutation[second]) for first, second in graph.edges}
    )
    return LogicalGraph(graph.num_vertices, tuple(colors), edges)


def _adjacency(graph: LogicalGraph) -> tuple[set[int], ...]:
    adjacency: tuple[set[int], ...] = tuple(set() for _ in range(graph.num_vertices))
    for first, second in graph.edges:
        adjacency[first].add(second)
        adjacency[second].add(first)
    return adjacency


def _component_vertices(adjacency: tuple[set[int], ...]) -> list[tuple[int, ...]]:
    unseen = set(range(len(adjacency)))
    components: list[tuple[int, ...]] = []
    while unseen:
        start = min(unseen)
        unseen.remove(start)
        queue = deque([start])
        component: list[int] = []
        while queue:
            vertex = queue.popleft()
            component.append(vertex)
            for neighbor in adjacency[vertex]:
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    queue.append(neighbor)
        components.append(tuple(sorted(component)))
    return components


def _is_bipartite(adjacency: tuple[set[int], ...]) -> bool:
    side: list[int | None] = [None] * len(adjacency)
    for start in range(len(adjacency)):
        if side[start] is not None:
            continue
        side[start] = 0
        queue = deque([start])
        while queue:
            vertex = queue.popleft()
            for neighbor in adjacency[vertex]:
                if side[neighbor] is None:
                    side[neighbor] = 1 - side[vertex]  # type: ignore[operator]
                    queue.append(neighbor)
                elif side[neighbor] == side[vertex]:
                    return False
    return True


def _local_signature(
    adjacency: tuple[set[int], ...], vertex: int, *, count_triangles: bool
) -> tuple[Any, ...]:
    neighbors = sorted(adjacency[vertex])
    neighbor_set = set(neighbors)
    local_adjacency = {neighbor: adjacency[neighbor] & neighbor_set for neighbor in neighbors}
    local_edges = sum(len(values) for values in local_adjacency.values()) // 2
    local_degrees = tuple(sorted(len(values) for values in local_adjacency.values()))
    unseen = set(neighbors)
    component_sizes: list[int] = []
    while unseen:
        start = min(unseen)
        unseen.remove(start)
        queue = [start]
        size = 0
        while queue:
            current = queue.pop()
            size += 1
            for neighbor in local_adjacency[current]:
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    queue.append(neighbor)
        component_sizes.append(size)
    triangles = -1
    if count_triangles:
        triangles = 0
        for first in neighbors:
            for second in local_adjacency[first]:
                if second <= first:
                    continue
                triangles += sum(
                    1
                    for third in local_adjacency[first] & local_adjacency[second]
                    if third > second
                )
    return (
        len(neighbors),
        local_edges,
        local_degrees,
        tuple(sorted(component_sizes)),
        triangles,
    )


def _try_cfi_parity(graph: LogicalGraph, adjacency: tuple[set[int], ...]) -> int | None:
    color_classes: dict[int, set[int]] = {}
    for vertex, color in enumerate(graph.colors):
        color_classes.setdefault(color, set()).add(vertex)
    if len(color_classes) != 2:
        return None
    class_values = list(color_classes.values())
    middle: set[int] | None = None
    outer: set[int] | None = None
    for candidate_middle, candidate_outer in (
        (class_values[0], class_values[1]),
        (class_values[1], class_values[0]),
    ):
        if (
            len(candidate_middle) * 3 == len(candidate_outer) * 2
            and all(not (adjacency[v] & candidate_middle) for v in candidate_middle)
            and all(len(adjacency[v] & candidate_outer) == 1 for v in candidate_outer)
        ):
            middle, outer = candidate_middle, candidate_outer
            break
    if middle is None or outer is None:
        return None

    gadget_adjacency = tuple(
        {
            neighbor
            for neighbor in adjacency[vertex]
            if graph.colors[neighbor] != graph.colors[vertex]
        }
        for vertex in range(graph.num_vertices)
    )
    gadgets = _component_vertices(gadget_adjacency)
    if not gadgets or any(len(component) != 10 for component in gadgets):
        return None

    gadget_of: dict[int, int] = {}
    pair_of: dict[int, tuple[int, int]] = {}
    parity = 0
    for gadget_id, component in enumerate(gadgets):
        gadget_middle = sorted(set(component) & middle)
        gadget_outer = sorted(set(component) & outer)
        if len(gadget_middle) != 4 or len(gadget_outer) != 6:
            return None
        middle_set = frozenset(gadget_middle)
        by_neighborhood: dict[frozenset[int], int] = {}
        for vertex in gadget_outer:
            neighborhood = frozenset(adjacency[vertex] & middle)
            if len(neighborhood) != 2 or neighborhood in by_neighborhood:
                return None
            by_neighborhood[neighborhood] = vertex
            gadget_of[vertex] = gadget_id
        unused = set(gadget_outer)
        pairs: list[tuple[int, int]] = []
        while unused:
            first = min(unused)
            complement = middle_set - frozenset(adjacency[first] & middle)
            second = by_neighborhood.get(complement)
            if second is None or second == first or second not in unused:
                return None
            unused.remove(first)
            unused.remove(second)
            pairs.append((min(first, second), max(first, second)))
        if len(pairs) != 3:
            return None
        pairs.sort()
        chosen_middle = gadget_middle[0]
        gadget_parity = 0
        for pair_id, (zero_port, one_port) in enumerate(pairs):
            pair_of[zero_port] = (pair_id, 0)
            pair_of[one_port] = (pair_id, 1)
            if chosen_middle in adjacency[one_port]:
                gadget_parity ^= 1
            elif chosen_middle not in adjacency[zero_port]:
                return None
        parity ^= gadget_parity

    cross_groups: dict[tuple[tuple[int, int], tuple[int, int]], list[tuple[int, int]]] = {}
    for first, second in graph.edges:
        if first not in outer or second not in outer:
            continue
        first_incidence = (gadget_of[first], pair_of[first][0])
        second_incidence = (gadget_of[second], pair_of[second][0])
        if first_incidence == second_incidence:
            return None
        if first_incidence < second_incidence:
            key = (first_incidence, second_incidence)
            bits = (pair_of[first][1], pair_of[second][1])
        else:
            key = (second_incidence, first_incidence)
            bits = (pair_of[second][1], pair_of[first][1])
        cross_groups.setdefault(key, []).append(bits)
    expected_incidences = 3 * len(gadgets)
    used_incidences: set[tuple[int, int]] = set()
    if len(cross_groups) * 2 != expected_incidences:
        return None
    for (first_incidence, second_incidence), connections in cross_groups.items():
        if (
            len(connections) != 2
            or first_incidence in used_incidences
            or second_incidence in used_incidences
        ):
            return None
        used_incidences.add(first_incidence)
        used_incidences.add(second_incidence)
        xor_values = {first_bit ^ second_bit for first_bit, second_bit in connections}
        if len(xor_values) != 1 or {first_bit for first_bit, _ in connections} != {0, 1}:
            return None
        parity ^= xor_values.pop()
    return parity


def _maximal_six_cliques(
    component: tuple[int, ...], adjacency: tuple[set[int], ...]
) -> list[frozenset[int]] | None:
    local_of = {vertex: index for index, vertex in enumerate(component)}
    local_adjacency = [0] * len(component)
    for vertex, index in local_of.items():
        mask = 0
        for neighbor in adjacency[vertex]:
            if neighbor in local_of:
                mask |= 1 << local_of[neighbor]
        local_adjacency[index] = mask
    found: set[frozenset[int]] = set()
    aborted = False

    def search(clique: int, candidates: int, excluded: int) -> None:
        nonlocal aborted
        if aborted or clique.bit_count() > 6 or clique.bit_count() + candidates.bit_count() < 6:
            return
        if not candidates and not excluded:
            if clique.bit_count() == 6:
                found.add(
                    frozenset(
                        component[index] for index in range(len(component)) if clique >> index & 1
                    )
                )
                if len(found) > 64:
                    aborted = True
            return
        pivot_pool = candidates | excluded
        if pivot_pool:
            pivot = max(
                (index for index in range(len(component)) if pivot_pool >> index & 1),
                key=lambda index: (candidates & local_adjacency[index]).bit_count(),
            )
            branch = candidates & ~local_adjacency[pivot]
        else:
            branch = candidates
        while branch:
            bit = branch & -branch
            vertex = bit.bit_length() - 1
            search(
                clique | bit,
                candidates & local_adjacency[vertex],
                excluded & local_adjacency[vertex],
            )
            candidates &= ~bit
            excluded |= bit
            branch &= ~bit

    search(0, (1 << len(component)) - 1, 0)
    if aborted:
        return None
    return sorted(found, key=lambda clique: tuple(sorted(clique)))


def _try_line_root_signature(
    graph: LogicalGraph, adjacency: tuple[set[int], ...], components: list[tuple[int, ...]]
) -> tuple[Any, ...] | None:
    if not components or any(
        len(component) != 48 or any(len(adjacency[vertex]) != 10 for vertex in component)
        for component in components
    ):
        return None
    component = components[0]
    star_cliques = _maximal_six_cliques(component, adjacency)
    if star_cliques is None or len(star_cliques) != 16:
        return None
    memberships: dict[int, list[int]] = {vertex: [] for vertex in component}
    for clique_id, clique in enumerate(star_cliques):
        for vertex in clique:
            memberships[vertex].append(clique_id)
    if any(len(values) != 2 or values[0] == values[1] for values in memberships.values()):
        return None
    root_edges: set[tuple[int, int]] = {
        (min(values[0], values[1]), max(values[0], values[1])) for values in memberships.values()
    }
    if len(root_edges) != 48:
        return None
    root = LogicalGraph(16, (0,) * 16, tuple(sorted(root_edges)))
    root_adjacency = _adjacency(root)
    if any(len(neighbors) != 6 for neighbors in root_adjacency):
        return None
    reconstructed_line_edges: set[tuple[int, int]] = set()
    ordered_component = list(component)
    for left_index, left in enumerate(ordered_component):
        left_stars = set(memberships[left])
        for right in ordered_component[left_index + 1 :]:
            if left_stars & set(memberships[right]):
                reconstructed_line_edges.add((min(left, right), max(left, right)))
    actual_edges = {
        (first, second)
        for first, second in graph.edges
        if first in memberships and second in memberships
    }
    if reconstructed_line_edges != actual_edges:
        return None
    return tuple(
        sorted(
            _local_signature(root_adjacency, vertex, count_triangles=True) for vertex in range(16)
        )
    )


def public_graph_fingerprint(graph: LogicalGraph | Mapping[str, object]) -> tuple[Any, ...]:
    """Compute a public-only invariant sufficient for all supported T2.1 cases.

    No case identifier, logical coordinates, private metadata, or hidden source bit is
    consulted.  The specialized CFI and line-root recognizers first validate their
    complete public grammar and return no value for unrelated graphs.
    """

    parsed = graph if isinstance(graph, LogicalGraph) else parse_public_graph(graph)
    _validate_logical_graph(parsed)
    adjacency = _adjacency(parsed)
    components = _component_vertices(adjacency)
    degree_histogram = tuple(sorted(Counter(map(len, adjacency)).items()))
    color_histogram = tuple(sorted(Counter(parsed.colors).items()))

    # The local type multiset is a genuine relabelling invariant and separates the
    # Shrikhande/rook and Doob/Hamming pairs.  The q=32 Latin family is detected
    # from its public size/degree profile and uses its vertex-transitive anchor to
    # avoid recomputing an expensive K4 count at all 1024 vertices.
    latin_order = isqrt(parsed.num_vertices)
    latin_profile = (
        latin_order * latin_order == parsed.num_vertices
        and latin_order >= 4
        and len(parsed.edges) == 3 * latin_order * (latin_order * (latin_order - 1) // 2)
        and degree_histogram == ((3 * (latin_order - 1), parsed.num_vertices),)
        and len(color_histogram) == 1
    )
    if latin_profile:
        local_types: tuple[Any, ...] = ()
        anchor_triangle_count = _local_signature(adjacency, 0, count_triangles=True)[-1]
    else:
        local_types = tuple(
            sorted(
                Counter(
                    _local_signature(adjacency, vertex, count_triangles=False)
                    for vertex in range(parsed.num_vertices)
                ).items()
            )
        )
        anchor_triangle_count = None

    cfi_parity = _try_cfi_parity(parsed, adjacency)
    line_root_signature = _try_line_root_signature(parsed, adjacency, components)
    return (
        parsed.num_vertices,
        len(parsed.edges),
        color_histogram,
        degree_histogram,
        tuple(sorted(len(component) for component in components)),
        _is_bipartite(adjacency),
        local_types,
        anchor_triangle_count,
        cfi_parity,
        line_root_signature,
    )
