from __future__ import annotations

from pathlib import Path

import pikepdf

from ..core.errors import ToolError
from .base import SECURITY, Choice, Flag, Password, Tool


def run(source: Path, ctx) -> list[Path]:
    o = ctx.options
    user = o.get("password") or ""
    owner = o.get("owner_password") or ""
    if not user and not owner:
        raise ToolError("Enter a password.")
    everything_allowed = all(bool(o.get(k, True)) for k in ("print", "copy", "modify"))
    if not owner:
        # A random permissions password stops anyone from lifting the restrictions.
        import secrets

        owner = user if everything_allowed else secrets.token_urlsafe(24)
    allow = pikepdf.Permissions(
        print_lowres=bool(o.get("print", True)),
        print_highres=bool(o.get("print", True)),
        extract=bool(o.get("copy", True)),
        accessibility=True,
        modify_annotation=bool(o.get("modify", True)),
        modify_form=bool(o.get("modify", True)),
        modify_other=bool(o.get("modify", True)),
        modify_assembly=bool(o.get("modify", True)),
    )
    strength = o.get("strength", "aes256")
    r = 6 if strength == "aes256" else 4
    pdf = ctx.open_pdf(source)
    enc = pikepdf.Encryption(user=user, owner=owner, R=r, allow=allow, aes=True, metadata=True)
    return [ctx.save_pdf(pdf, ctx.output_path(source, " (protected)"), encryption=enc)]


TOOL = Tool(
    id="protect",
    name="Protect PDF",
    category=SECURITY,
    description="Lock a PDF with a password so only people who know it can open it.",
    icon="lock",
    run=run,
    chainable=True,
    keywords="encrypt password secure lock",
    options=[
        Password("password", "Password to open", "", confirm=True),
        Flag("print", "Allow printing", True),
        Flag("copy", "Allow copying text and images", True),
        Flag("modify", "Allow editing, comments and forms", True),
        Password("owner_password", "Permissions password (optional)", "",
                 help="Needed to change the permissions above. If empty, the opening password is used, "
                      "or a random one when something is restricted."),
        Choice("strength", "Encryption", "aes256", choices=[("aes256", "AES 256-bit (recommended)"),
                                                            ("aes128", "AES 128-bit (older readers)")]),
    ],
)

