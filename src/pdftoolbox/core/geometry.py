"""Page geometry helpers shared by the stamping tools."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VisibleBox:
    """The visible area of a page (its CropBox) and how it is rotated."""

    x0: float
    y0: float
    x1: float
    y1: float
    rotate: int  # 0, 90, 180 or 270 (clockwise, as displayed)

    @property
    def width(self) -> float:
        """Width as the reader sees it."""
        w, h = self.x1 - self.x0, self.y1 - self.y0
        return h if self.rotate in (90, 270) else w

    @property
    def height(self) -> float:
        w, h = self.x1 - self.x0, self.y1 - self.y0
        return w if self.rotate in (90, 270) else h

    def matrix(self, src_w: float, src_h: float) -> tuple[float, float, float, float, float, float]:
        """Matrix mapping a (src_w x src_h) upright overlay onto the visible page.

        The overlay is scaled to exactly cover the visible area and rotated so
        that its top edge is at the top of the page as displayed.
        """
        sx = self.width / src_w if src_w else 1.0
        sy = self.height / src_h if src_h else 1.0
        x0, y0, x1, y1 = self.x0, self.y0, self.x1, self.y1
        if self.rotate == 90:
            base = (0, 1, -1, 0, x1, y0)
        elif self.rotate == 180:
            base = (-1, 0, 0, -1, x1, y1)
        elif self.rotate == 270:
            base = (0, -1, 1, 0, x0, y1)
        else:
            base = (1, 0, 0, 1, x0, y0)
        a, b, c, d, e, f = base
        # Pre-multiply by the scale matrix [sx 0 0 sy 0 0].
        return (a * sx, b * sx, c * sy, d * sy, e, f)


def inherited(page_obj, key: str):
    """Look up a page attribute, following the /Parent chain like viewers do."""
    node, depth = page_obj, 0
    while node is not None and depth < 64:
        value = node.get(key)
        if value is not None:
            return value
        node = node.get("/Parent")
        depth += 1
    return None


def _box(value):
    try:
        x0, y0, x1, y1 = (float(v) for v in value)
        return x0, y0, x1, y1
    except Exception:  # noqa: BLE001 - missing or malformed box
        return None


def page_visible_box(page) -> VisibleBox:
    """Build a VisibleBox from a pikepdf Page."""
    obj = page.obj
    media = _box(inherited(obj, "/MediaBox")) or (0.0, 0.0, 612.0, 792.0)
    crop = _box(inherited(obj, "/CropBox")) or media
    x0, y0, x1, y1 = crop
    mx0, my0, mx1, my1 = media
    # Clip the crop box to the media box, as viewers do.
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    mx0, mx1 = sorted((mx0, mx1))
    my0, my1 = sorted((my0, my1))
    x0, y0, x1, y1 = max(x0, mx0), max(y0, my0), min(x1, mx1), min(y1, my1)
    if x1 <= x0 or y1 <= y0:
        x0, y0, x1, y1 = mx0, my0, mx1, my1
    try:
        rotate = int(inherited(obj, "/Rotate") or 0) % 360
    except Exception:  # noqa: BLE001
        rotate = 0
    if rotate not in (0, 90, 180, 270):
        rotate = 0
    return VisibleBox(x0, y0, x1, y1, rotate)
