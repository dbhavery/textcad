"""OpenSCAD rendering + export. The OpenSCAD binary is invoked as an external
tool (no library linkage), so nothing built on textcad inherits OpenSCAD's GPL."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger("textcad.render")
REPO_ROOT = Path(__file__).resolve().parent.parent


def find_openscad() -> str | None:
    """Locate the OpenSCAD binary: $TEXTCAD_OPENSCAD, PATH, a bundled portable
    copy under tools/openscad-*/, then standard Windows install dirs."""
    env = os.environ.get("TEXTCAD_OPENSCAD")
    if env and Path(env).exists():
        return env
    for name in ("openscad", "openscad.exe", "openscad.com"):
        p = shutil.which(name)
        if p:
            return p
    candidates = [
        *REPO_ROOT.glob("tools/openscad-*/openscad.exe"),
        Path(r"C:/Program Files/OpenSCAD/openscad.exe"),
        Path(r"C:/Program Files/OpenSCAD (Nightly)/openscad.exe"),
        Path(r"C:/Program Files/OpenSCAD/openscad.com"),
        Path("/usr/bin/openscad"),
        Path("/usr/local/bin/openscad"),
    ]
    for c in candidates:
        if Path(c).exists():
            return str(c)
    return None


def _run(openscad: str, scad: Path, out: Path, extra: list[str]) -> tuple[bool, str]:
    cmd = [openscad, "-o", str(out), *extra, str(scad)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    ok = proc.returncode == 0 and out.exists() and out.stat().st_size > 0
    return ok, (proc.stderr or proc.stdout or "").strip()


def render_png(openscad: str, scad: Path, png: Path) -> tuple[bool, str]:
    """Default isometric preview render."""
    return _run(openscad, scad, png, [
        "--autocenter", "--viewall", "--imgsize=1024,768",
        "--colorscheme=Tomorrow", "--render",
    ])


def _ortho(openscad: str, scad: Path, png: Path, eye: str) -> tuple[bool, str]:
    """Orthographic render from an eye position looking at the origin. --viewall
    auto-fits, so only the eye *direction* matters."""
    return _run(openscad, scad, png, [
        "--projection=o", f"--camera={eye},0,0,0", "--viewall", "--autocenter",
        "--imgsize=1024,768", "--colorscheme=Tomorrow", "--render",
    ])


def render_top_png(openscad: str, scad: Path, png: Path) -> tuple[bool, str]:
    """Straight top-down orthographic view. A foreshortened isometric makes small
    vision models misread polygons (a hexagon reads as 'rectangular'); a top view
    makes the cross-section unambiguous for the inspector."""
    return _ortho(openscad, scad, png, "0,0,100")


def render_front_png(openscad: str, scad: Path, png: Path) -> tuple[bool, str]:
    """Front orthographic view (looking along +Y) — shows the XZ face."""
    return _ortho(openscad, scad, png, "0,-100,0")


def render_right_png(openscad: str, scad: Path, png: Path) -> tuple[bool, str]:
    """Right-side orthographic view (looking along -X) — shows the YZ face."""
    return _ortho(openscad, scad, png, "100,0,0")


# Labelled view set fed to the inspector. Top catches cross-section/polygon shape;
# front + side catch features on the vertical faces (legs, side grooves, bottom
# bores). Larger CAD systems render several orthographic views for the same reason.
VIEWS = (
    ("top-down", render_top_png),
    ("front", render_front_png),
    ("right-side", render_right_png),
)


def render_views(openscad: str, scad: Path, base: Path) -> list[tuple[str, Path]]:
    """Render the labelled multi-view set next to `base` (e.g. out/part).
    Returns [(label, png_path), ...] for views that rendered successfully."""
    out: list[tuple[str, Path]] = []
    for label, fn in VIEWS:
        png = base.with_name(f"{base.name}_{label.replace('-', '')}.png")
        ok, _ = fn(openscad, scad, png)
        if ok:
            out.append((label, png))
    return out


def make_contact_sheet(views: list[tuple[str, Path]], out: Path, height: int = 360) -> Path | None:
    """Composite labelled views side-by-side into ONE image (an orthographic
    'contact sheet', like an engineering drawing). Small vision models judge a
    single labelled image far more reliably than several separate images. Needs
    Pillow (`pip install textcad[inspect]`); returns None if unavailable/empty."""
    if not views:
        return None
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        log.warning("Pillow not installed — `pip install textcad[inspect]` for contact sheets")
        return None
    scaled = []
    for label, p in views:
        im = Image.open(p).convert("RGB")
        w = max(1, int(im.width * height / im.height))
        scaled.append((label, im.resize((w, height))))
    pad, label_h = 12, 28
    total_w = sum(im.width for _, im in scaled) + pad * (len(scaled) + 1)
    canvas = Image.new("RGB", (total_w, height + label_h + pad), (245, 245, 245))
    draw = ImageDraw.Draw(canvas)
    x = pad
    for label, im in scaled:
        canvas.paste(im, (x, label_h))
        draw.text((x + 4, 6), label.upper(), fill=(20, 20, 20))
        x += im.width + pad
    canvas.save(out)
    return out


def export_stl(openscad: str, scad: Path, stl: Path) -> tuple[bool, str]:
    """Export a binary STL. Failure here (with a successful preview) usually means
    mixed 2D/3D or non-manifold geometry — a real defect worth feeding back."""
    return _run(openscad, scad, stl, ["--export-format=binstl"])
