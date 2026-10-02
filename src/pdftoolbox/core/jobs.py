"""Run a tool over its input files, in-process or inside a worker process."""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any, Callable

from .context import Context, FileResult, JobSpec
from .errors import Cancelled, ToolError


def _friendly(exc: BaseException) -> str:
    if isinstance(exc, ToolError):
        return str(exc)
    if isinstance(exc, MemoryError):
        return "The computer ran out of memory while processing this file."
    if isinstance(exc, PermissionError):
        return f"Permission denied: {exc.filename or exc}. Is the file open in another program?"
    if isinstance(exc, OSError) and getattr(exc, "strerror", None):
        return f"{exc.strerror}: {exc.filename}" if exc.filename else str(exc.strerror)
    return f"{type(exc).__name__}: {exc}"


def execute(
    spec: JobSpec,
    report: Callable[[str, Any], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> list[FileResult]:
    """Run ``spec`` and return one result per input (or one for COMBINE tools).

    Errors in one file do not stop the others. Cancellation raises Cancelled.
    """
    from pdftoolbox.tools import get_tool
    from pdftoolbox.tools.base import COMBINE

    tool = get_tool(spec.tool_id)
    ctx = Context(spec, report, is_cancelled)
    results: list[FileResult] = []
    try:
        if tool.check:
            problem = tool.check()
            if problem:
                raise ToolError(problem)
        if tool.mode == COMBINE:
            ctx.set_file(0, 1)
            result = FileResult(source=", ".join(Path(f).name for f in spec.files))
            try:
                out = tool.run([Path(f) for f in spec.files], ctx)
                _store(result, out)
            except Cancelled:
                raise
            except Exception as exc:  # noqa: BLE001 - shown to the user
                result.error = _friendly(exc)
                result.message = None
                if not isinstance(exc, ToolError):
                    result.message = traceback.format_exc(limit=8)
            result.message = result.message or ("\n".join(ctx.notes) or None)
            results.append(result)
            ctx.progress(1.0)
        else:
            count = len(spec.files)
            for index, name in enumerate(spec.files):
                ctx.set_file(index, count)
                ctx.notes = []
                source = Path(name)
                ctx.progress(0.0, f"{source.name} ({index + 1} of {count})")
                result = FileResult(source=str(source))
                try:
                    out = tool.run(source, ctx)
                    _store(result, out)
                except Cancelled:
                    raise
                except Exception as exc:  # noqa: BLE001 - shown to the user
                    result.error = _friendly(exc)
                    if not isinstance(exc, ToolError):
                        result.message = traceback.format_exc(limit=8)
                if not result.error and ctx.notes:
                    result.message = "\n".join(ctx.notes)
                results.append(result)
                if report:
                    report("file-done", result)
            ctx.set_file(count - 1 if count else 0, count or 1)
            ctx.progress(1.0)
    finally:
        ctx.cleanup()
    return results


def _store(result: FileResult, out) -> None:
    if out is None:
        return
    if isinstance(out, dict):
        result.report = out.get("report")
        result.outputs = [str(p) for p in out.get("outputs", [])]
        return
    if isinstance(out, (str, Path)):
        result.outputs = [str(out)]
        return
    result.outputs = [str(p) for p in out]


def worker_main(spec: JobSpec, queue, cancel_event) -> None:
    """Entry point of the worker process."""
    from .stamp import prepare_headless_qt

    prepare_headless_qt()

    def report(kind: str, payload: Any) -> None:
        queue.put((kind, payload))

    try:
        results = execute(spec, report, cancel_event.is_set)
        queue.put(("done", results))
    except Cancelled:
        queue.put(("cancelled", None))
    except BaseException as exc:  # noqa: BLE001 - report everything to the UI
        queue.put(("failed", f"{_friendly(exc)}\n\n{traceback.format_exc(limit=10)}"))
