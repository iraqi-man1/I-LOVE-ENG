"""Registry of every tool in the application."""

from __future__ import annotations

import importlib

from .base import Tool

# Modules are listed explicitly (rather than discovered) so the frozen
# application bundles them and the order on screen is stable.
TOOL_MODULES = (
    "merge",
    "split",
    "extract_pages",
    "delete_pages",
    "organize",
    "rotate",
    "crop",
    "pdf_to_image",
    "image_to_pdf",
    "extract_images",
    "office",
    "watermark",
    "page_numbers",
    "header_footer",
    "metadata",
    "grayscale",
    "compress",
    "optimize",
    "repair",
    "ocr",
    "info",
    "protect",
    "unlock",
    "batch",
)

_registry: dict[str, Tool] | None = None


def all_tools() -> list[Tool]:
    global _registry
    if _registry is None:
        _registry = {}
        for name in TOOL_MODULES:
            module = importlib.import_module(f"{__name__}.{name}")
            tools = getattr(module, "TOOLS", None) or [module.TOOL]
            for tool in tools:
                if tool.id in _registry:
                    raise RuntimeError(f"Duplicate tool id {tool.id}")
                _registry[tool.id] = tool
    return list(_registry.values())


def get_tool(tool_id: str) -> Tool:
    all_tools()
    assert _registry is not None
    try:
        return _registry[tool_id]
    except KeyError:
        raise KeyError(f"Unknown tool {tool_id!r}") from None
