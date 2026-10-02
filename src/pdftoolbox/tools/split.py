from __future__ import annotations

from pathlib import Path

import pikepdf

from ..core.errors import ToolError
from ..core.pages import parse_groups
from .base import ORGANIZE, Choice, Integer, Text, Tool


def _write(ctx, src: pikepdf.Pdf, indexes: list[int], path: Path) -> Path:
    out = pikepdf.new()
    for i in indexes:
        out.pages.append(src.pages[i])
    return ctx.save_pdf(out, path)


def _bookmark_groups(src: pikepdf.Pdf) -> list[tuple[str, int]]:
    starts: list[tuple[str, int]] = []
    with src.open_outline() as outline:
        for item in outline.root:
            try:
                dest = item.destination
                if dest is None and item.action is not None:
                    dest = item.action.get("/D")
                page_ref = None
                if isinstance(dest, pikepdf.Array) and len(dest):
                    page_ref = dest[0]
                elif dest is not None:
                    resolved = src.Root.get("/Dests", {}).get(dest) if not isinstance(dest, pikepdf.Array) else None
                    if isinstance(resolved, pikepdf.Array) and len(resolved):
                        page_ref = resolved[0]
                if page_ref is None:
                    continue
                index = pikepdf.Page(page_ref).index if not isinstance(page_ref, int) else int(page_ref)
                starts.append((item.title, index))
            except Exception:  # noqa: BLE001 - skip bookmarks we cannot resolve
                continue
    starts.sort(key=lambda s: s[1])
    return starts


def run(source: Path, ctx) -> list[Path]:
    mode = ctx.options.get("mode", "each")
    src = ctx.open_pdf(source)
    total = len(src.pages)
    groups: list[tuple[str, list[int]]] = []
    if mode == "each":
        groups = [(f"page {i + 1}", [i]) for i in range(total)]
    elif mode == "every":
        n = max(1, int(ctx.options.get("every", 2)))
        groups = [(f"pages {i + 1}-{min(i + n, total)}", list(range(i, min(i + n, total)))) for i in range(0, total, n)]
    elif mode == "ranges":
        for g in parse_groups(ctx.options.get("ranges", ""), total):
            label = f"pages {g[0] + 1}-{g[-1] + 1}" if len(g) > 1 else f"page {g[0] + 1}"
            groups.append((label, g))
    elif mode == "bookmarks":
        starts = _bookmark_groups(src)
        if not starts:
            raise ToolError("This PDF has no top-level bookmarks to split by.")
        if starts[0][1] > 0:
            starts.insert(0, ("Start", 0))
        for k, (title, first) in enumerate(starts):
            last = starts[k + 1][1] if k + 1 < len(starts) else total
            if last > first:
                groups.append((title, list(range(first, last))))
    elif mode == "parts":
        parts = max(1, min(total, int(ctx.options.get("parts", 2))))
        size, extra = divmod(total, parts)
        start = 0
        for k in range(parts):
            end = start + size + (1 if k < extra else 0)
            groups.append((f"part {k + 1}", list(range(start, end))))
            start = end
    folder = ctx.output_subfolder(source, " (split)")
    outputs = []
    width = len(str(len(groups)))
    for k, (label, indexes) in enumerate(groups):
        ctx.progress(k / len(groups), f"Writing {label}")
        name = f"{k + 1:0{width}d} - {source.stem} - {label}" if mode == "bookmarks" else f"{source.stem} - {label}"
        from ..core.context import safe_name, unique_path

        outputs.append(_write(ctx, src, indexes, unique_path(folder / f"{safe_name(name)}.pdf")))
    return outputs


TOOL = Tool(
    id="split",
    name="Split PDF",
    category=ORGANIZE,
    description="Break a PDF into several files: every page, every few pages, by ranges or by bookmarks.",
    icon="split",
    run=run,
    keywords="separate divide burst",
    options=[
        Choice("mode", "Split", "each", choices=[
            ("each", "Into single pages"),
            ("every", "Every N pages"),
            ("parts", "Into N equal parts"),
            ("ranges", "By page ranges"),
            ("bookmarks", "By top-level bookmarks"),
        ]),
        Integer("every", "Pages per file", 2, minimum=1, maximum=100000, visible_when=("mode", ("every",))),
        Integer("parts", "Number of parts", 2, minimum=2, maximum=10000, visible_when=("mode", ("parts",))),
        Text("ranges", "Page ranges", "", placeholder="e.g. 1-3, 4-10, 11-",
             help="Each range becomes its own file. Use ; to put several ranges in one file (1-2,5; 3-4).",
             visible_when=("mode", ("ranges",))),
    ],
)
