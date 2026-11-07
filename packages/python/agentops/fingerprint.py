"""Deterministic SHA-256 fingerprints for JSON-like tool actions."""
import hashlib
import json
from collections.abc import Mapping
from typing import Any

_MAX_SAFE_INTEGER = (1 << 53) - 1


def _normalize(value: Any, path: str = "action") -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        value.encode("utf-8", errors="strict")
        return value
    if isinstance(value, int):
        if not -_MAX_SAFE_INTEGER <= value <= _MAX_SAFE_INTEGER:
            raise ValueError(f"{path} integers must be JavaScript-safe")
        return value
    if isinstance(value, float):
        raise TypeError(f"{path} floating-point values are not supported; use integer minor units or strings")
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError(f"{path} object keys must be strings")
        # JavaScript string ordering uses UTF-16 code units. Match that ordering
        # rather than Python's Unicode code-point ordering for supplementary keys.
        keys = sorted(value, key=lambda key: key.encode("utf-16-be", errors="strict"))
        return {key: _normalize(value[key], f"{path}.{key}") for key in keys}
    if isinstance(value, (list, tuple)):
        return [_normalize(item, f"{path}[{index}]") for index, item in enumerate(value)]
    raise TypeError(f"{path} contains a value that is not JSON-compatible")


def canonical_action_json(action: Mapping[str, Any]) -> str:
    if not isinstance(action, Mapping):
        raise TypeError("action must be a mapping with string keys")
    normalized = _normalize(action)
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"), sort_keys=False)


def action_fingerprint(action: Mapping[str, Any]) -> str:
    """Return SHA-256 over the cross-language canonical action representation."""
    return hashlib.sha256(canonical_action_json(action).encode("utf-8")).hexdigest()
