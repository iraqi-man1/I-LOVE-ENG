"""Building blocks for tools.

A tool is a plain description (name, inputs, options) plus a function that
does the work. The user interface builds its form from the options, and the
job runner calls the function in a separate worker process, so a slow or
crashing document never freezes the window.

Adding a tool:
  1. Create a module in ``pdftoolbox/tools``.
  2. Define a ``TOOL = Tool(...)`` at module level.
  3. List the module in ``pdftoolbox/tools/__init__.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

# ----------------------------------------------------------------------------
# Input kinds
# ----------------------------------------------------------------------------

PDF = "pdf"
IMAGE = "image"
WORD = "word"
EXCEL = "excel"
POWERPOINT = "powerpoint"

EXTENSIONS: dict[str, tuple[str, ...]] = {
    PDF: (".pdf",),
    IMAGE: (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp"),
    WORD: (".doc", ".docx", ".docm", ".odt", ".rtf", ".txt"),
    EXCEL: (".xls", ".xlsx", ".xlsm", ".ods", ".csv"),
    POWERPOINT: (".ppt", ".pptx", ".pptm", ".odp", ".pps", ".ppsx"),
}

KIND_LABELS = {
    PDF: "PDF files",
    IMAGE: "Images",
    WORD: "Word documents",
    EXCEL: "Excel spreadsheets",
    POWERPOINT: "PowerPoint presentations",
}

# Categories, in the order they appear in the sidebar.
ORGANIZE = "Organize"
CONVERT = "Convert"
EDIT = "Edit"
SECURITY = "Security"
OPTIMIZE = "Optimize"
CATEGORIES = (ORGANIZE, CONVERT, EDIT, OPTIMIZE, SECURITY)

# ----------------------------------------------------------------------------
# Options
# ----------------------------------------------------------------------------


@dataclass
class Option:
    key: str
    label: str
    default: Any = None
    help: str = ""
    # Show this option only when another option has one of these values.
    visible_when: tuple[str, tuple] | None = None
    # Keep the value between sessions (passwords never are).
    remember: bool = True

    def is_visible(self, values: dict[str, Any]) -> bool:
        if not self.visible_when:
            return True
        key, allowed = self.visible_when
        return values.get(key) in allowed


@dataclass
class Choice(Option):
    choices: Sequence[tuple[Any, str]] = ()


@dataclass
class Integer(Option):
    minimum: int = 0
    maximum: int = 100000
    suffix: str = ""


@dataclass
class Number(Option):
    minimum: float = 0.0
    maximum: float = 100000.0
    decimals: int = 1
    suffix: str = ""


@dataclass
class Flag(Option):
    pass


@dataclass
class Text(Option):
    placeholder: str = ""
    multiline: bool = False


@dataclass
class Pages(Option):
    """A page selection such as "1-3, 5". Empty means every page."""

    placeholder: str = "All pages (or e.g. 1-3, 5, 8-)"


@dataclass
class Password(Option):
    confirm: bool = False
    remember: bool = False


@dataclass
class Color(Option):
    pass


@dataclass
class Font(Option):
    pass


@dataclass
class ImageFile(Option):
    pass


@dataclass
class Languages(Option):
    """OCR languages, filled from the installed Tesseract data."""


@dataclass
class PageOrganizer(Option):
    """Visual page grid: drag to reorder, rotate, delete. Needs one PDF."""

    remember: bool = False


@dataclass
class Pipeline(Option):
    """A list of steps for the batch tool."""

    remember: bool = True


# ----------------------------------------------------------------------------
# Tools
# ----------------------------------------------------------------------------

EACH = "each"  # the function runs once per input file
COMBINE = "combine"  # the function receives every input file at once


@dataclass
class Tool:
    id: str
    name: str
    category: str
    description: str
    run: Callable[..., Any]
    icon: str = "file"
    inputs: tuple[str, ...] = (PDF,)
    options: list[Option] = field(default_factory=list)
    mode: str = EACH
    min_files: int = 1
    max_files: int | None = None
    # Output is a single PDF per input, so the tool can be a batch step.
    chainable: bool = False
    # The tool produces a report rather than files (for example PDF information).
    report: bool = False
    # For COMBINE tools: default output file name (without extension) and extension.
    output_name: str = "output"
    output_ext: str = ".pdf"
    # Optional: return option values to prefill when a single file is chosen.
    prefill: Callable[[str, str | None], dict[str, Any]] | None = None
    # Optional: return an error message when a requirement is missing (e.g. Tesseract).
    check: Callable[[], str | None] | None = None
    keywords: str = ""
    # Hidden tools are used by other screens (for example Scan) and not listed.
    hidden: bool = False

    def accepts(self, path: str) -> bool:
        lower = path.lower()
        return any(lower.endswith(ext) for kind in self.inputs for ext in EXTENSIONS[kind])

    @property
    def extensions(self) -> tuple[str, ...]:
        return tuple(ext for kind in self.inputs for ext in EXTENSIONS[kind])

    def defaults(self) -> dict[str, Any]:
        return {o.key: o.default for o in self.options}
