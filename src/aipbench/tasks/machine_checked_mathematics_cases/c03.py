"""C03: reconstruct a hidden root from a twice-iterated line graph."""

from __future__ import annotations

import itertools
from collections.abc import Mapping, Sequence
from typing import Any, Final

from aipbench.tasks.machine_checked_mathematics_cases.common import (
    DeterministicStream,
    LeanCaseBlueprint,
    challenge_source,
    integer_parameter,
    lean_nat_list,
    lean_pair_list,
)

CASE_ID: Final = "c03"
TITLE: Final = "Hidden line-graph root certificate"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {"base_vertices": 64}


def _edge_sequence(problem: Mapping[str, Any]) -> tuple[tuple[int, int], ...]:
    raw_edges = problem["edges"]
    if not isinstance(raw_edges, Sequence) or isinstance(raw_edges, (str, bytes)):
        raise ValueError("line-graph edges must be a sequence")
    edges: list[tuple[int, int]] = []
    for raw_edge in raw_edges:
        if (
            not isinstance(raw_edge, Sequence)
            or isinstance(raw_edge, (str, bytes))
            or len(raw_edge) != 2
        ):
            raise ValueError("line-graph edges must be pairs")
        left, right = raw_edge
        if (
            isinstance(left, bool)
            or not isinstance(left, int)
            or isinstance(right, bool)
            or not isinstance(right, int)
        ):
            raise ValueError("line-graph endpoints must be integers")
        edges.append((left, right))
    return tuple(edges)


def _line_graph_edges(edges: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    incident: dict[int, list[int]] = {}
    for edge_id, (left, right) in enumerate(edges):
        incident.setdefault(left, []).append(edge_id)
        incident.setdefault(right, []).append(edge_id)
    line_edges: set[tuple[int, int]] = set()
    for edge_ids in incident.values():
        for left, right in itertools.combinations(edge_ids, 2):
            line_edges.add((min(left, right), max(left, right)))
    return sorted(line_edges)


def _lean_pair_blocks(edges: Sequence[tuple[int, int]], block_size: int = 96) -> str:
    blocks = [edges[index : index + block_size] for index in range(0, len(edges), block_size)]
    return "[\n    " + ",\n    ".join(lean_pair_list(block) for block in blocks) + "\n  ]"


def _lean_range_blocks(length: int, block_size: int = 64) -> str:
    blocks = [
        range(index, min(index + block_size, length)) for index in range(0, length, block_size)
    ]
    return "[\n    " + ",\n    ".join(lean_nat_list(block) for block in blocks) + "\n  ]"


def _adjacency(num_vertices: int, edges: Sequence[tuple[int, int]]) -> list[set[int]]:
    adjacency = [set() for _ in range(num_vertices)]
    seen: set[tuple[int, int]] = set()
    for left, right in edges:
        if left < 0 or right < 0 or left >= num_vertices or right >= num_vertices or left >= right:
            raise ValueError("public graph edges must be ordered, loop-free, and in range")
        if (left, right) in seen:
            raise ValueError("public graph edges must be distinct")
        seen.add((left, right))
        adjacency[left].add(right)
        adjacency[right].add(left)
    return adjacency


def solve(problem: Mapping[str, Any]) -> tuple[int, ...]:
    num_public_vertices = problem["num_public_vertices"]
    num_root_vertices = problem["num_root_vertices"]
    if (
        isinstance(num_public_vertices, bool)
        or not isinstance(num_public_vertices, int)
        or isinstance(num_root_vertices, bool)
        or not isinstance(num_root_vertices, int)
        or num_public_vertices < 4
        or num_root_vertices < 4
    ):
        raise ValueError("line-graph vertex counts must be nontrivial integers")
    edges = _edge_sequence(problem)
    adjacency = _adjacency(num_public_vertices, edges)

    cliques: set[tuple[int, int, int, int]] = set()
    for first in range(num_public_vertices):
        for triple in itertools.combinations(sorted(adjacency[first]), 3):
            candidate = tuple(sorted((first, *triple)))
            if candidate[0] != first:
                continue
            if all(
                right in adjacency[left] for left, right in itertools.combinations(candidate, 2)
            ):
                cliques.add(candidate)
    ordered_cliques = sorted(cliques)
    if len(ordered_cliques) != num_root_vertices:
        raise ValueError("public graph does not expose the expected four-clique root")

    memberships: list[list[int]] = [[] for _ in range(num_public_vertices)]
    for clique_id, clique in enumerate(ordered_cliques):
        for vertex in clique:
            memberships[vertex].append(clique_id)
    endpoint_pairs: list[tuple[int, int]] = []
    for membership in memberships:
        if len(membership) != 2:
            raise ValueError("each public vertex must lie in exactly two root cliques")
        endpoint_pairs.append((min(membership), max(membership)))

    if len(set(endpoint_pairs)) != num_public_vertices:
        raise ValueError("recovered root contains duplicate edges")
    if any(not (set(endpoint_pairs[left]) & set(endpoint_pairs[right])) for left, right in edges):
        raise AssertionError("recovered endpoint pairs do not realize every public edge")
    pair_codes = tuple(left * num_root_vertices + right for left, right in endpoint_pairs)
    code_base = num_root_vertices * num_root_vertices
    codes_per_word = 8
    return tuple(
        sum(
            code * code_base**offset
            for offset, code in enumerate(pair_codes[start : start + codes_per_word])
        )
        for start in range(0, num_public_vertices, codes_per_word)
    )


def build(stream: DeterministicStream, parameters: Mapping[str, Any]) -> LeanCaseBlueprint:
    base_vertices = integer_parameter(parameters, "base_vertices", minimum=8, maximum=320)
    if base_vertices % 2 != 0:
        raise ValueError("base_vertices must be even")
    half = base_vertices // 2
    if half < 4:
        raise ValueError("base graph needs at least four vertices per side")

    labels = list(range(base_vertices))
    stream.shuffle(labels)
    left_labels = labels[:half]
    right_labels = labels[half:]
    right_order = list(range(half))
    stream.shuffle(right_order)
    third_shift = stream.randint(2, half - 1)
    base_edges = sorted(
        {
            tuple(
                sorted(
                    (
                        left_labels[index],
                        right_labels[right_order[(index + shift) % half]],
                    )
                )
            )
            for index in range(half)
            for shift in (0, 1, third_shift)
        }
    )
    if len(base_edges) != 3 * half:
        raise AssertionError("base cubic graph generation produced duplicate edges")
    stream.shuffle(base_edges)
    first_line_edges = _line_graph_edges(base_edges)
    stream.shuffle(first_line_edges)
    public_edges = _line_graph_edges(first_line_edges)
    stream.shuffle(public_edges)

    num_root_vertices = len(base_edges)
    num_public_vertices = len(first_line_edges)
    codes_per_word = 8
    num_packed_words = (num_public_vertices + codes_per_word - 1) // codes_per_word
    problem = {
        "num_public_vertices": num_public_vertices,
        "num_root_vertices": num_root_vertices,
        "edges": [list(edge) for edge in public_edges],
    }
    certificate = solve(problem)
    declarations = f"""def numPublicVertices : Nat := {num_public_vertices}
def numRootVertices : Nat := {num_root_vertices}
def publicEdgeBlocks : List (List (Nat × Nat)) := {_lean_pair_blocks(public_edges)}
def publicVertexBlocks : List (List Nat) := {_lean_range_blocks(num_public_vertices)}
def rootVertexBlocks : List (List Nat) := {_lean_range_blocks(num_root_vertices)}
def codeBase : Nat := numRootVertices * numRootVertices
def codesPerWord : Nat := {codes_per_word}
def numPackedWords : Nat := {num_packed_words}

def pairCode (certificate : List Nat) (vertex : Nat) : Nat :=
  ((certificate.getD (vertex / codesPerWord) 0) /
    (codeBase ^ (vertex % codesPerWord))) % codeBase

def endpointA (certificate : List Nat) (vertex : Nat) : Nat :=
  pairCode certificate vertex / numRootVertices

def endpointB (certificate : List Nat) (vertex : Nat) : Nat :=
  pairCode certificate vertex % numRootVertices

def packedWordsWellFormed (certificate : List Nat) : Bool :=
  certificate.all (fun word => word < codeBase ^ codesPerWord)

def pairsWellFormed (certificate : List Nat) : Bool :=
  publicVertexBlocks.all (fun block =>
    block.all (fun vertex =>
      endpointA certificate vertex < endpointB certificate vertex &&
      endpointB certificate vertex < numRootVertices))

def incidentCountBlock
    (certificate : List Nat) (rootVertex : Nat) (block : List Nat) : Nat :=
  block.foldl (fun total vertex =>
    if endpointA certificate vertex == rootVertex ||
       endpointB certificate vertex == rootVertex then total + 1 else total) 0

def incidentCount (certificate : List Nat) (rootVertex : Nat) : Nat :=
  publicVertexBlocks.foldl (fun total block =>
    total + incidentCountBlock certificate rootVertex block) 0

def rootIsFourRegular (certificate : List Nat) : Bool :=
  rootVertexBlocks.all (fun block =>
    block.all (fun rootVertex => incidentCount certificate rootVertex == 4))

def shareEndpoint (certificate : List Nat) (left right : Nat) : Bool :=
  endpointA certificate left == endpointA certificate right ||
  endpointA certificate left == endpointB certificate right ||
  endpointB certificate left == endpointA certificate right ||
  endpointB certificate left == endpointB certificate right

def publicEdgesHold (certificate : List Nat) : Bool :=
  publicEdgeBlocks.all (fun block =>
    block.all (fun edge =>
      edge.1 < numPublicVertices && edge.2 < numPublicVertices &&
      shareEndpoint certificate edge.1 edge.2))

abbrev ProfileEncoded : Prop :=
  numPublicVertices = numRootVertices * 2 ∧
  numRootVertices = {num_root_vertices}"""
    predicate = """abbrev valid (certificate : List Nat) : Prop :=
  certificate.length = numPackedWords ∧
  packedWordsWellFormed certificate = true ∧
  pairsWellFormed certificate = true ∧
  rootIsFourRegular certificate = true ∧
  publicEdgesHold certificate = true"""
    source = challenge_source(
        declarations=declarations,
        predicate=predicate,
        claim="ProfileEncoded",
    )
    source = source.replace(
        "\nend Challenge\n",
        """

theorem submit (certificate : List Nat) (hValid : valid certificate) : Target := by
  exact Exists.intro certificate (And.intro hValid (by decide))

end Challenge
""",
    )
    return LeanCaseBlueprint(
        title=TITLE,
        problem=problem,
        challenge_source=source,
        reference_certificate=certificate,
        public_features={"vertices": num_public_vertices, "edges": len(public_edges)},
        metadata={
            "criterion": "double_line_graph_four_clique_root",
            "base_vertices": base_vertices,
            "root_vertices": num_root_vertices,
            "certificate_entries": len(certificate),
            "decoded_pairs": num_public_vertices,
        },
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "TITLE", "build", "solve"]
