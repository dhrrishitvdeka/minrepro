"""Tests for structural tree ops (shipped minrepro.model)."""

from __future__ import annotations

import pytest

from minrepro.model import (
    Path,
    count_stats,
    delete_at,
    deep_copy,
    get_at,
    iter_deletion_candidates,
    kind_of,
    NodeKind,
)


def test_kind_of():
    assert kind_of({}) is NodeKind.MAPPING
    assert kind_of([]) is NodeKind.SEQUENCE
    assert kind_of("x") is NodeKind.SCALAR
    assert kind_of(1) is NodeKind.SCALAR
    assert kind_of(None) is NodeKind.SCALAR


def test_path_str_identifiers_and_special_keys():
    assert str(Path()) == "$"
    assert str(Path(("services", "backend"))) == "$.services.backend"
    assert str(Path(("ports", 0))) == "$.ports[0]"
    assert "weird-key" in str(Path(("weird-key",)))


def test_deep_copy_is_independent():
    root = {"a": [1, {"b": 2}]}
    clone = deep_copy(root)
    clone["a"][1]["b"] = 99
    assert root["a"][1]["b"] == 2


def test_delete_mapping_key():
    root = {"keep": 1, "drop": 2}
    out = delete_at(root, Path(("drop",)))
    assert out == {"keep": 1}
    assert root == {"keep": 1, "drop": 2}  # original untouched


def test_delete_sequence_item():
    root = {"ports": ["a", "b", "c"]}
    out = delete_at(root, Path(("ports", 1)))
    assert out == {"ports": ["a", "c"]}


def test_delete_nested():
    root = {
        "services": {
            "frontend": {"image": "f"},
            "backend": {"image": "b", "env": {"BAD": True}},
        }
    }
    out = delete_at(root, Path(("services", "frontend")))
    assert "frontend" not in out["services"]
    assert out["services"]["backend"]["env"]["BAD"] is True


def test_delete_root_raises():
    with pytest.raises(ValueError):
        delete_at({"a": 1}, Path())


def test_get_at():
    root = {"a": {"b": [10, 20]}}
    assert get_at(root, Path(("a", "b", 1))) == 20


def test_iter_candidates_covers_keys_and_items():
    root = {
        "services": {
            "frontend": {"ports": ["3000:3000"]},
            "backend": {"env": {"X": 1}},
        }
    }
    cands = list(iter_deletion_candidates(root))
    labels = {c.label for c in cands}
    kinds = {c.kind for c in cands}
    assert "key" in kinds
    assert "item" in kinds
    assert any("frontend" in lab for lab in labels)
    assert any("[0]" in lab for lab in labels)
    # Larger subtrees first
    assert cands[0].size_hint >= cands[-1].size_hint


def test_count_stats():
    root = {"a": [1, 2], "b": {"c": 3}}
    stats = count_stats(root)
    assert stats.mappings == 2
    assert stats.sequences == 1
    assert stats.scalars == 3
    assert stats.keys == 3  # a, b, c
    assert stats.items == 2
    assert stats.nodes == 6
