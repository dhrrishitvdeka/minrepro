"""Shared fixtures for minrepro tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
ORACLE_BAD = EXAMPLES / "oracle_bad_option.py"
ORACLE_OK = EXAMPLES / "oracle_always_ok.py"
BROKEN_YAML = EXAMPLES / "broken.yaml"
BROKEN_JSON = EXAMPLES / "broken.json"


@pytest.fixture
def repo_root() -> Path:
    return ROOT


@pytest.fixture
def examples_dir() -> Path:
    return EXAMPLES


@pytest.fixture
def oracle_bad_cmd() -> str:
    """Portable shell command using the current interpreter."""
    return f'"{sys.executable}" "{ORACLE_BAD}" {{}}'


@pytest.fixture
def oracle_ok_cmd() -> str:
    return f'"{sys.executable}" "{ORACLE_OK}" {{}}'


@pytest.fixture
def broken_yaml() -> Path:
    return BROKEN_YAML


@pytest.fixture
def broken_json() -> Path:
    return BROKEN_JSON
