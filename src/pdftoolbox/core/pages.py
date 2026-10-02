"""Parse page selections such as "1-3, 7, 10-", "odd", "even" or "last"."""

from __future__ import annotations

import re

from .errors import ToolError

_TOKEN = re.compile(r"^(\d+|last|end)?\s*(-)?\s*(\d+|last|end)?$")


def _num(token: str | None, total: int) -> int | None:
    if token is None:
        return None
    if token in ("last", "end"):
        return total
    return int(token)


def parse_pages(spec: str | None, total: int, *, allow_empty: bool = False) -> list[int]:
    """Return zero-based page indexes, in the order written, without duplicates.

    An empty selection means every page unless ``allow_empty`` is set.
    """
    spec = (spec or "").strip().lower()
    if not spec or spec == "all":
        return [] if allow_empty and not spec else list(range(total))
    result: list[int] = []
    seen: set[int] = set()

    def add(index: int) -> None:
        if index not in seen:
            seen.add(index)
            result.append(index)

    for part in re.split(r"[,;]+", spec):
        part = part.strip()
        if not part:
            continue
        if part == "all":
            for i in range(total):
                add(i)
            continue
        if part in ("odd", "even"):
            start = 0 if part == "odd" else 1
            for i in range(start, total, 2):
                add(i)
            continue
        m = _TOKEN.match(part)
        if not m or (m.group(1) is None and m.group(3) is None):
            raise ToolError(f"“{part}” is not a valid page selection. Use something like 1-3, 5, 8-.")
        first, dash, last = _num(m.group(1), total), m.group(2), _num(m.group(3), total)
        if not dash:
            first = last = first if first is not None else last
        first = 1 if first is None else first
        last = total if last is None else last
        if first < 1 or last < 1:
            raise ToolError("Page numbers start at 1.")
        if first > total or last > total:
            raise ToolError(f"The document has {total} page{'s' if total != 1 else ''}; “{part}” is out of range.")
        step = 1 if last >= first else -1
        for p in range(first, last + step, step):
            add(p - 1)
    if not result and not allow_empty:
        raise ToolError("No pages were selected.")
    return result


def parse_groups(spec: str, total: int) -> list[list[int]]:
    """Parse "1-3; 4-6, 9" style input into groups (one output file per group).

    Groups are separated by ";" or new lines. A single comma-separated list of
    plain ranges ("1-3, 4-6") is also treated as one group per range.
    """
    spec = (spec or "").strip()
    if not spec:
        raise ToolError("Enter the page ranges to split by, for example 1-3, 4-8, 9-.")
    if ";" in spec or "\n" in spec:
        chunks = [c for c in re.split(r"[;\n]+", spec) if c.strip()]
    else:
        chunks = [c for c in spec.split(",") if c.strip()]
    return [parse_pages(c, total) for c in chunks]
