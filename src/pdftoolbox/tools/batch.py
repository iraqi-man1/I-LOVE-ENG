"""Run several tools one after another on many files."""

from __future__ import annotations

import shutil
from pathlib import Path

from ..core.context import Context, JobSpec
from ..core.errors import ToolError
from .base import OPTIMIZE, Pipeline, Text, Tool


def chainable_tools():
    from . import all_tools

    return [t for t in all_tools() if t.chainable]


def run(source: Path, ctx) -> list[Path]:
    from . import get_tool

    steps = ctx.options.get("steps") or []
    if not steps:
        raise ToolError("Add at least one step.")
    current = source
    password = ctx.password_for(source)
    work = ctx.temp_dir / f"batch-{abs(hash(str(source)))}"
    work.mkdir(parents=True, exist_ok=True)
    for k, step in enumerate(steps):
        tool = get_tool(step["tool"])
        if not tool.chainable:
            raise ToolError(f"“{tool.name}” cannot be used as a batch step.")
        if tool.check:
            problem = tool.check()
            if problem:
                raise ToolError(problem)
        options = {**tool.defaults(), **(step.get("options") or {})}
        spec = JobSpec(tool.id, [str(current)], options, passwords={str(current): password} if password else {})

        def report(kind, payload, k=k, name=tool.name):
            if kind == "progress":
                fraction, message = payload
                ctx.progress((k + fraction) / len(steps), f"{name}: {message}" if message else name)

        sub = Context(spec, report, ctx._is_cancelled)
        sub.forced_output_path = work / f"step {k + 1}.pdf"
        sub.forced_output_dir = work / f"step {k + 1}"
        try:
            outputs = tool.run(current, sub)
        finally:
            sub.cleanup()
        outputs = [Path(p) for p in (outputs or []) if str(p).lower().endswith(".pdf")]
        if not outputs:
            raise ToolError(f"Step {k + 1} ({tool.name}) produced no PDF.")
        current = outputs[0]
        for note in sub.notes:
            ctx.note(f"{tool.name}: {note}")
        if tool.id == "protect":
            password = options.get("password") or options.get("owner_password") or None
        elif tool.id == "unlock":
            password = None
    final = ctx.output_path(source, ctx.options.get("suffix") or " (processed)")
    shutil.copyfile(current, final)
    return [final]


TOOL = Tool(
    id="batch",
    name="Batch processing",
    category=OPTIMIZE,
    description="Apply a chain of steps (for example rotate, watermark, compress) to many PDFs at once.",
    icon="batch",
    run=run,
    keywords="bulk many multiple automate chain workflow",
    options=[
        Pipeline("steps", "Steps", []),
        Text("suffix", "Add to file names", " (processed)"),
    ],
)
