"""The object a tool receives while it runs."""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .errors import Cancelled, PasswordRequired, ToolError


@dataclass
class JobSpec:
    """Everything a worker needs to run one job. Must stay picklable."""

    tool_id: str
    files: list[str]
    options: dict[str, Any]
    output_dir: str | None = None  # None: next to each source file
    output_file: str | None = None  # COMBINE tools: the exact output path
    passwords: dict[str, str] = field(default_factory=dict)
    suffix: str | None = None  # file-name suffix for EACH tools


@dataclass
class FileResult:
    source: str
    outputs: list[str] = field(default_factory=list)
    error: str | None = None
    message: str | None = None
    report: str | None = None


def unique_path(path: Path) -> Path:
    """Return ``path`` or, if it exists, ``name (2).ext``, ``name (3).ext`` ..."""
    if not path.exists():
        return path
    stem, ext = path.stem, path.suffix
    n = 2
    while True:
        candidate = path.with_name(f"{stem} ({n}){ext}")
        if not candidate.exists():
            return candidate
        n += 1


def safe_name(name: str) -> str:
    bad = '<>:"/\\|?*\0'
    cleaned = "".join("_" if c in bad or ord(c) < 32 else c for c in name).strip(" .")
    return cleaned or "output"


class Context:
    def __init__(
        self,
        spec: JobSpec,
        report: Callable[[str, Any], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ):
        self.spec = spec
        self.options: dict[str, Any] = dict(spec.options)
        self._report = report or (lambda kind, payload: None)
        self._is_cancelled = is_cancelled or (lambda: False)
        self._file_index = 0
        self._file_count = max(1, len(spec.files))
        self._last_progress = 0.0
        self._tmp: Path | None = None
        self.notes: list[str] = []
        # Set by the batch tool so a step writes into its own folder.
        self.forced_output_dir: Path | None = None
        self.forced_output_path: Path | None = None

    # -- progress -----------------------------------------------------------

    def set_file(self, index: int, count: int | None = None) -> None:
        self._file_index = index
        if count:
            self._file_count = count

    def progress(self, fraction: float, message: str | None = None) -> None:
        """Report progress of the current file (0..1)."""
        self.check_cancel()
        fraction = min(1.0, max(0.0, fraction))
        overall = (self._file_index + fraction) / self._file_count
        now = time.monotonic()
        if message or now - self._last_progress > 0.1 or fraction >= 1.0:
            self._last_progress = now
            self._report("progress", (overall, message))

    def check_cancel(self) -> None:
        if self._is_cancelled():
            raise Cancelled()

    def note(self, message: str) -> None:
        """Add a message shown to the user next to the result."""
        self.notes.append(message)

    # -- files --------------------------------------------------------------

    @property
    def temp_dir(self) -> Path:
        if self._tmp is None:
            self._tmp = Path(tempfile.mkdtemp(prefix="pdftoolbox-"))
        return self._tmp

    def cleanup(self) -> None:
        if self._tmp is not None:
            shutil.rmtree(self._tmp, ignore_errors=True)
            self._tmp = None

    def output_folder(self, source: Path) -> Path:
        if self.forced_output_dir is not None:
            folder = self.forced_output_dir
        elif self.spec.output_dir:
            folder = Path(self.spec.output_dir)
        else:
            folder = source.parent
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def output_path(self, source: Path, suffix: str, ext: str = ".pdf") -> Path:
        """A new, non-clashing path for the result made from ``source``."""
        if self.forced_output_path is not None:
            return self.forced_output_path
        if self.spec.suffix is not None:
            suffix = self.spec.suffix
        folder = self.output_folder(source)
        return unique_path(folder / f"{safe_name(source.stem + suffix)}{ext}")

    def output_subfolder(self, source: Path, suffix: str) -> Path:
        """A new folder for tools that produce many files from one source."""
        folder = unique_path(self.output_folder(source) / safe_name(source.stem + suffix))
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def combined_output_path(self, default_name: str, ext: str) -> Path:
        if self.forced_output_path is not None:
            return self.forced_output_path
        if self.spec.output_file:
            path = Path(self.spec.output_file)
            path.parent.mkdir(parents=True, exist_ok=True)
            return path
        first = Path(self.spec.files[0]) if self.spec.files else Path.home() / "x"
        folder = self.output_folder(first)
        return unique_path(folder / f"{safe_name(default_name)}{ext}")

    def password_for(self, path: Path) -> str | None:
        return self.spec.passwords.get(str(path))

    # -- PDF helpers --------------------------------------------------------

    def open_pdf(self, path: Path, **kwargs):
        """Open a PDF with pikepdf, using a password the user supplied."""
        import pikepdf

        password = self.password_for(path) or ""
        try:
            return pikepdf.open(path, password=password, **kwargs)
        except pikepdf.PasswordError:
            raise PasswordRequired(path.name) from None
        except FileNotFoundError:
            raise ToolError(f"“{path}” could not be found.") from None
        except pikepdf.PdfError as exc:
            raise ToolError(
                f"“{path.name}” could not be read as a PDF ({exc}). Try the Repair PDF tool first."
            ) from None

    def save_pdf(self, pdf, path: Path, **kwargs) -> Path:
        """Save atomically: write a temporary file then move it into place."""
        import pikepdf

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.part")
        options = dict(
            object_stream_mode=pikepdf.ObjectStreamMode.generate,
            compress_streams=True,
        )
        # Edited copies of a protected PDF stay protected with the same passwords.
        if getattr(pdf, "is_encrypted", False) and "encryption" not in kwargs:
            options["encryption"] = True
        options.update(kwargs)
        try:
            pdf.save(tmp, **options)
            os.replace(tmp, path)
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
        return path
