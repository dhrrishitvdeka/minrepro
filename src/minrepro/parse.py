"""Load and dump JSON/YAML configuration documents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

import yaml

Format = Literal["json", "yaml"]


class ParseError(ValueError):
    """Raised when input is not valid JSON or YAML structured data."""


def detect_format(path: Path, explicit: Format | None = None) -> Format:
    if explicit is not None:
        return explicit
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix in {".yaml", ".yml"}:
        return "yaml"
    # Peek at content
    text = path.read_text(encoding="utf-8").lstrip()
    if text.startswith("{") or text.startswith("["):
        return "json"
    return "yaml"


def load(path: Path, fmt: Format | None = None) -> tuple[Any, Format, str]:
    # utf-8-sig strips a Windows BOM if present; newline=None keeps \n/\r\n text.
    text = path.read_text(encoding="utf-8-sig")
    resolved = detect_format(path, fmt)
    data = loads(text, resolved)
    return data, resolved, text



def loads(text: str, fmt: Format) -> Any:
    if fmt == "json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ParseError(f"invalid JSON: {exc}") from exc
    else:
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ParseError(f"invalid YAML: {exc}") from exc

    if data is None:
        raise ParseError("document is empty")
    if not isinstance(data, (dict, list)):
        raise ParseError(
            f"root must be a mapping or sequence, got {type(data).__name__}"
        )
    _assert_json_compatible(data)
    return data


def _assert_json_compatible(value: Any, path: str = "$") -> None:
    """Reject non-JSON-compatible values (dates, binary, sets, custom tags, etc.).

    minrepro only shrinks JSON-compatible trees: nested mappings/sequences of
    str/int/float/bool/null. YAML date/datetime, !!binary, sets, and other
    PyYAML objects are rejected with a clear ParseError.
    """
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, (str, int, float, bool)) and k is not None:
                raise ParseError(
                    f"unsupported mapping key type at {path}: {type(k).__name__} "
                    f"(only JSON-compatible keys: str/int/float/bool/null)"
                )
            _assert_json_compatible(v, f"{path}.{k}")
    elif isinstance(value, list):
        for i, item in enumerate(value):
            _assert_json_compatible(item, f"{path}[{i}]")
    elif isinstance(value, (str, int, float, bool)) or value is None:
        return
    else:
        raise ParseError(
            f"unsupported value type at {path}: {type(value).__name__} "
            f"(minrepro accepts JSON-compatible YAML/JSON only: "
            f"mappings, sequences, str, int, float, bool, null; "
            f"not date/datetime, binary, sets, or custom tags)"
        )


def dumps(data: Any, fmt: Format, *, indent: int = 2) -> str:
    if fmt == "json":
        return json.dumps(data, indent=indent, ensure_ascii=False) + "\n"
    # default_flow_style=False keeps nested structure readable
    return yaml.safe_dump(
        data,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=120,
    )


def dump(path: Path, data: Any, fmt: Format) -> None:
    # Always write UTF-8 with LF-friendly content (JSON/YAML dumps use \n).
    # newline="\n" keeps output identical on Windows and Linux checkouts.
    path.write_text(dumps(data, fmt), encoding="utf-8", newline="\n")
