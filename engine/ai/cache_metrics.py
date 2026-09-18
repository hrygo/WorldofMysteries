"""Provider usage is observed evidence, not inferred from matching local strings."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class CacheUsage:
    total_input: int | None
    cache_read: int | None
    cache_write: int | None
    uncached: int | None
    valid: bool = True

    @property
    def hit_rate(self) -> float | None:
        if not self.valid or self.total_input is None or self.cache_read is None or self.total_input == 0:
            return None
        return self.cache_read / self.total_input


def normalize_usage(usage: Mapping[str, Any] | None, format: str) -> CacheUsage:
    if usage is None:
        return CacheUsage(None, None, None, None)
    valid = True

    def number(value: Any) -> int | None:
        nonlocal valid
        if value is None:
            return None
        if type(value) is not int or value < 0:
            valid = False
            return None
        return value

    total = read = write = uncached = None
    if format in {"openai_chat", "openai_responses"}:
        name = "prompt_tokens" if format == "openai_chat" else "input_tokens"
        total = number(usage.get(name))
        details = usage.get(name + "_details", {})
        if not isinstance(details, Mapping):
            details, valid = {}, False
        read, write = number(details.get("cached_tokens")), number(details.get("cache_write_tokens"))
        # Absence of write accounting is unknown (e.g. older endpoints), not zero.
        if None not in (total, read, write):
            uncached = total - read - write  # type: ignore[operator]
    elif format == "claude":
        uncached = number(usage.get("input_tokens"))
        read, write = number(usage.get("cache_read_input_tokens")), number(usage.get("cache_creation_input_tokens"))
        if None not in (uncached, read, write):
            total = uncached + read + write  # type: ignore[operator]
    elif format == "deepseek":
        total = number(usage.get("prompt_tokens"))
        read = number(usage.get("prompt_cache_hit_tokens"))
        uncached = number(usage.get("prompt_cache_miss_tokens"))
        if total is None and read is not None and uncached is not None:
            total = read + uncached
        if None not in (total, read, uncached) and total != read + uncached:
            valid = False
    if total is not None and read is not None and read > total:
        valid = False
    if uncached is not None and uncached < 0:
        uncached, valid = None, False
    return CacheUsage(total, read, write, uncached, valid)


def aggregate_hit_rate(usages: Iterable[CacheUsage]) -> float | None:
    """Do not silently omit unmeasured/invalid calls to inflate a dashboard rate."""
    total = cached = 0
    for item in usages:
        if not item.valid or item.total_input is None or item.cache_read is None:
            return None
        total += item.total_input
        cached += item.cache_read
    return cached / total if total else None
