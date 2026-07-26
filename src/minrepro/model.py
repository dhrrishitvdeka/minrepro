"""Tree model for structured configuration documents."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterator


class NodeKind(str, Enum):
    MAPPING = "mapping"
    SEQUENCE = "sequence"
    SCALAR = "scalar"


@dataclass
class Path:
    """Location of a node inside a config tree.

    Segments are either mapping keys (str | int | float | bool | None for JSON/YAML)
    or sequence indices (int). Mixed for nested structures.
    """

    segments: tuple[Any, ...] = ()

    def child(self, segment: Any) -> Path:
        return Path(self.segments + (segment,))

    def __str__(self) -> str:
        if not self.segments:
            return "$"
        parts: list[str] = ["$"]
        for seg in self.segments:
            # Convention: int segment -> [n] (list index or integer map key);
            # identifier strings -> .key; other keys -> ['repr'].
            if isinstance(seg, int) and not isinstance(seg, bool):
                parts.append(f"[{seg}]")
            else:
                key = str(seg)
                if key.isidentifier():
                    parts.append(f".{key}")
                else:
                    parts.append(f"[{key!r}]")
        return "".join(parts)

    def __hash__(self) -> int:
        return hash(self.segments)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Path) and self.segments == other.segments


@dataclass
class Stats:
    mappings: int = 0
    sequences: int = 0
    scalars: int = 0
    keys: int = 0
    items: int = 0

    @property
    def nodes(self) -> int:
        return self.mappings + self.sequences + self.scalars

    def as_dict(self) -> dict[str, int]:
        return {
            "nodes": self.nodes,
            "mappings": self.mappings,
            "sequences": self.sequences,
            "scalars": self.scalars,
            "keys": self.keys,
            "items": self.items,
        }


def kind_of(value: Any) -> NodeKind:
    if isinstance(value, dict):
        return NodeKind.MAPPING
    if isinstance(value, list):
        return NodeKind.SEQUENCE
    return NodeKind.SCALAR


def count_stats(value: Any) -> Stats:
    stats = Stats()
    _walk_stats(value, stats)
    return stats


def _walk_stats(value: Any, stats: Stats) -> None:
    k = kind_of(value)
    if k is NodeKind.MAPPING:
        stats.mappings += 1
        stats.keys += len(value)
        for v in value.values():
            _walk_stats(v, stats)
    elif k is NodeKind.SEQUENCE:
        stats.sequences += 1
        stats.items += len(value)
        for item in value:
            _walk_stats(item, stats)
    else:
        stats.scalars += 1


def deep_copy(value: Any) -> Any:
    """JSON-safe deep copy (dicts, lists, scalars only)."""
    if isinstance(value, dict):
        return {k: deep_copy(v) for k, v in value.items()}
    if isinstance(value, list):
        return [deep_copy(v) for v in value]
    return value


def get_at(root: Any, path: Path) -> Any:
    cur = root
    for seg in path.segments:
        cur = cur[seg]
    return cur


def set_at(root: Any, path: Path, value: Any) -> None:
    if not path.segments:
        raise ValueError("cannot replace root via set_at")
    parent = get_at(root, Path(path.segments[:-1]))
    parent[path.segments[-1]] = value


def delete_at(root: Any, path: Path) -> Any:
    """Delete key or list item at path. Returns a new root tree."""
    if not path.segments:
        raise ValueError("cannot delete root")
    new_root = deep_copy(root)
    parent_path = Path(path.segments[:-1])
    parent = get_at(new_root, parent_path) if parent_path.segments else new_root
    key = path.segments[-1]
    if isinstance(parent, dict):
        del parent[key]
    elif isinstance(parent, list):
        del parent[int(key)]
    else:
        raise TypeError(f"cannot delete from {type(parent).__name__}")
    return new_root


@dataclass
class DeletionCandidate:
    """A single structural deletion: one mapping key or one sequence item."""

    path: Path
    kind: str  # "key" | "item"
    label: str
    size_hint: int = 1  # approximate subtree weight for ordering


def iter_deletion_candidates(root: Any) -> Iterator[DeletionCandidate]:
    """Yield all removable keys and list items, largest subtrees first."""
    candidates: list[DeletionCandidate] = []
    _collect(root, Path(), candidates)
    candidates.sort(key=lambda c: c.size_hint, reverse=True)
    yield from candidates


def _subtree_size(value: Any) -> int:
    k = kind_of(value)
    if k is NodeKind.MAPPING:
        return 1 + sum(_subtree_size(v) for v in value.values())
    if k is NodeKind.SEQUENCE:
        return 1 + sum(_subtree_size(v) for v in value)
    return 1


def _collect(value: Any, path: Path, out: list[DeletionCandidate]) -> None:
    k = kind_of(value)
    if k is NodeKind.MAPPING:
        for key, child in value.items():
            child_path = path.child(key)
            out.append(
                DeletionCandidate(
                    path=child_path,
                    kind="key",
                    label=str(child_path),
                    size_hint=_subtree_size(child),
                )
            )
            _collect(child, child_path, out)
    elif k is NodeKind.SEQUENCE:
        for idx, child in enumerate(value):
            child_path = path.child(idx)
            out.append(
                DeletionCandidate(
                    path=child_path,
                    kind="item",
                    label=str(child_path),
                    size_hint=_subtree_size(child),
                )
            )
            _collect(child, child_path, out)


@dataclass
class ReductionEvent:
    step: int
    path: str
    kind: str
    kept: bool
    reason: str
    exit_code: int | None = None
    bytes_before: int = 0
    bytes_after: int = 0


@dataclass
class ReductionResult:
    original: Any
    reduced: Any
    original_text: str
    reduced_text: str
    format: str
    events: list[ReductionEvent] = field(default_factory=list)
    oracle_runs: int = 0
    interesting_runs: int = 0
    duration_seconds: float = 0.0
    final_exit_code: int | None = None
    final_output: str = ""
    stopped_reason: str = "fixed-point"
