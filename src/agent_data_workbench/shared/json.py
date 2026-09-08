"""Canonical JSON, type-aware equality, and RFC 6901 evidence access."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


def pointer_parts(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/") or re.search(r"~(?![01])", pointer):
        raise ValueError(f"Invalid JSON pointer: {pointer}")
    return [part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")]


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def pointer_value(value: Any, pointer: str) -> Any:
    """Resolve RFC 6901, rejecting negative array indices and malformed escapes."""
    for part in pointer_parts(pointer):
        if isinstance(value, list):
            if not part.isascii() or not part.isdigit() or (len(part) > 1 and part[0] == "0"):
                raise ValueError(f"Invalid array index in pointer: {pointer}")
            try:
                value = value[int(part)]
            except IndexError as exc:
                raise ValueError(f"Missing pointer: {pointer}") from exc
        elif isinstance(value, dict) and part in value:
            value = value[part]
        else:
            raise ValueError(f"Missing pointer: {pointer}")
    return value


def _reject_constant(value: str) -> None:
    raise ValueError(f"Non-JSON numeric constant: {value}")


def json_equal(left: Any, right: Any) -> bool:
    # Python considers True == 1; JSON booleans and numbers have distinct semantics.
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(json_equal(left[k], right[k]) for k in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(json_equal(a, b) for a, b in zip(left, right))
    return (
        type(left) is type(right)
        and left == right
        or (type(left) in (int, float) and type(right) in (int, float) and left == right)
    )


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant)


def digest(value) -> str:
    return hashlib.sha256(json_text(value).encode()).hexdigest()


def parse_object(value: str) -> dict:
    obj = json.loads(value, parse_constant=_reject_constant)
    if not isinstance(obj, dict):
        raise ValueError("Expected a JSON object encoded as text")
    return obj
