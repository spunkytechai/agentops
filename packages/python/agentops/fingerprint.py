"""Deterministic SHA-256 fingerprints for JSON-like tool actions."""
import hashlib
import json
from collections.abc import Mapping
from typing import Any

_MAX_SAFE_INTEGER = (1 << 53) - 1


def _normalize(value: Any, path: str = "action") -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        if not -_MAX_SAFE_INTEGER <= value <= _MAX_SAFE_INTEGER:
            raise ValueError(f"{path} integers must be JavaScript-safe")
        return value
    if isinstance(value, float):
        raise TypeError(f"{path} floating-point values are not supported; use integer minor units or strings")
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError(f"{path} object keys must be strings")
        return {key: _normalize(value[key], f"{path}.{key}") for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_normalize(item, f"{path}[{index}]") for index, item in enumerate(value)]
    raise TypeError(f"{path} contains a value that is not JSON-compatible")


def canonical_action_json(action: Mapping[str, Any]) -> str:
    if not isinstance(action, Mapping):
        raise TypeError("action must be a mapping with string keys")
    normalized = _normalize(action)
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def action_fingerprint(action: Mapping[str, Any]) -> str:
    """Return SHA-256 over the cross-language canonical action representation."""
    return hashlib.sha256(canonical_action_json(action).encode("utf-8")).hexdigest()
