"""Load and dump JSON/YAML configuration documents."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Literal

import yaml

Format = Literal["json", "yaml"]

# YAML 1.1 implicit-boolean words. Used as mapping *keys* they must stay strings
# (GitHub Actions `on:`, Compose `no:` keys, etc.). Values still follow YAML 1.1.
_YAML11_BOOL_WORDS = frozenset(
    {
        "y",
        "Y",
        "yes",
        "Yes",
        "YES",
        "n",
        "N",
        "no",
        "No",
        "NO",
        "true",
        "True",
        "TRUE",
        "false",
        "False",
        "FALSE",
        "on",
        "On",
        "ON",
        "off",
        "Off",
        "OFF",
    }
)
_YAML11_BOOL_KEY_DUMP = re.compile(
    r"^(\s*)['\"]("
    + "|".join(re.escape(word) for word in sorted(_YAML11_BOOL_WORDS, key=len, reverse=True))
    + r")['\"]:",
    re.MULTILINE,
)


class ParseError(ValueError):
    """Raised when input is not valid JSON or YAML structured data."""


class _ConfigLoader(yaml.SafeLoader):
    """SafeLoader that keeps YAML 1.1 bool-words as string mapping keys."""


def _construct_mapping(loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if isinstance(key_node, yaml.ScalarNode) and isinstance(key, bool):
            # Preserve the written spelling (`on`, `yes`, `true`, ...).
            key = key_node.value
        value = loader.construct_object(value_node, deep=deep)
        mapping[key] = value
    return mapping


_ConfigLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


class _ConfigDumper(yaml.SafeDumper):
    """SafeDumper with default implicit resolvers.

    String keys that look like YAML 1.1 bool-words are quoted (``'on':``) so
    they stay strings under stock PyYAML. Boolean *values* dump as ``true`` /
    ``false``. The loader turns those quoted (and unquoted) key spellings back
    into the original string key, never ``true:``.
    """


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


def _reject_nonfinite_json(token: str) -> None:
    raise ParseError(f"non-finite JSON number: {token}")


def loads(text: str, fmt: Format) -> Any:
    if fmt == "json":
        try:
            data = json.loads(text, parse_constant=_reject_nonfinite_json)
        except json.JSONDecodeError as exc:
            raise ParseError(f"invalid JSON: {exc}") from exc
        except ParseError:
            raise
        except ValueError as exc:
            raise ParseError(f"invalid JSON: {exc}") from exc
    else:
        try:
            data = yaml.load(text, Loader=_ConfigLoader)
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
    """Reject non-JSON-compatible values (dates, binary, sets, NaN/Inf, tags).

    minrepro only shrinks finite JSON-compatible trees: nested mappings/sequences
    of str/int/finite-float/bool/null. YAML date/datetime, !!binary, sets,
    non-finite floats, and other PyYAML objects are rejected with ParseError.
    """
    if isinstance(value, dict):
        for k, v in value.items():
            if isinstance(k, float) and not math.isfinite(k):
                raise ParseError(f"non-finite mapping key at {path}: {k!r}")
            if not isinstance(k, (str, int, float, bool)) and k is not None:
                raise ParseError(
                    f"unsupported mapping key type at {path}: {type(k).__name__} "
                    f"(only JSON-compatible keys: str/int/float/bool/null)"
                )
            _assert_json_compatible(v, f"{path}.{k}")
    elif isinstance(value, list):
        for i, item in enumerate(value):
            _assert_json_compatible(item, f"{path}[{i}]")
    elif isinstance(value, bool) or value is None or isinstance(value, str):
        return
    elif isinstance(value, int) and not isinstance(value, bool):
        return
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ParseError(
                f"non-finite number at {path}: {value!r} "
                f"(NaN / Infinity are not JSON-compatible)"
            )
        return
    else:
        raise ParseError(
            f"unsupported value type at {path}: {type(value).__name__} "
            f"(minrepro accepts JSON-compatible YAML/JSON only: "
            f"mappings, sequences, str, int, float, bool, null; "
            f"not date/datetime, binary, sets, NaN/Infinity, or custom tags)"
        )


def dumps(data: Any, fmt: Format, *, indent: int = 2) -> str:
    if fmt == "json":
        return (
            json.dumps(
                data,
                indent=indent,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        )
    text = yaml.dump(
        data,
        Dumper=_ConfigDumper,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=120,
    )
    # Quote-stripping only on mapping keys: `'on':` → `on:` so dump+reload keeps
    # the written key and the file still looks like GitHub Actions / Compose.
    # Boolean *values* remain `true`/`false` (no trailing key colon).
    return _YAML11_BOOL_KEY_DUMP.sub(r"\1\2:", text)


def dump(path: Path, data: Any, fmt: Format) -> None:
    # Always write UTF-8 with LF-friendly content (JSON/YAML dumps use \n).
    # newline="\n" keeps output identical on Windows and Linux checkouts.
    path.write_text(dumps(data, fmt), encoding="utf-8", newline="\n")
