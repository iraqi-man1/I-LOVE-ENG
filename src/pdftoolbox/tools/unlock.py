from __future__ import annotations

from pathlib import Path

from ..core.errors import ToolError
from .base import SECURITY, Password, Tool


def run(source: Path, ctx) -> list[Path]:
    password = ctx.options.get("password") or ""
    if password and str(source) not in ctx.spec.passwords:
        ctx.spec.passwords[str(source)] = password
    pdf = ctx.open_pdf(source)
    if not pdf.is_encrypted:
        ctx.note("This PDF was not password protected; a copy was saved anyway.")
    elif not ctx.password_for(source):
        # Opened without a password: only permission restrictions were set.
        ctx.note("Removed the printing, copying and editing restrictions.")
    return [ctx.save_pdf(pdf, ctx.output_path(source, " (unlocked)"), encryption=False)]


def check_password(pdf_path: str, password: str) -> bool:
    import pikepdf

    try:
        pikepdf.open(pdf_path, password=password).close()
        return True
    except pikepdf.PasswordError:
        return False
    except Exception as exc:  # noqa: BLE001
        raise ToolError(str(exc)) from None


TOOL = Tool(
    id="unlock",
    name="Remove password",
    category=SECURITY,
    description="Save an unprotected copy of a PDF when you know its password.",
    icon="unlock",
    run=run,
    chainable=True,
    keywords="decrypt unlock unprotect remove password",
    options=[Password("password", "Current password", "",
                      help="Leave empty if the file opens without a password but blocks printing or copying.")],
)
