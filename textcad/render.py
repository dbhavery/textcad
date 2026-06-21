"""OpenSCAD rendering + export. The OpenSCAD binary is invoked as an external
tool (no library linkage), so nothing built on textcad inherits OpenSCAD's GPL."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

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


def render_top_png(openscad: str, scad: Path, png: Path) -> tuple[bool, str]:
    """Straight top-down orthographic view. A foreshortened isometric makes small
    vision models misread polygons (a hexagon reads as 'rectangular'); a top view
    makes the cross-section unambiguous for the inspector. (CADAM renders several
    orthographic views for the same reason.)"""
    return _run(openscad, scad, png, [
        "--projection=o", "--camera=0,0,100,0,0,0", "--viewall", "--autocenter",
        "--imgsize=1024,768", "--colorscheme=Tomorrow", "--render",
    ])


def export_stl(openscad: str, scad: Path, stl: Path) -> tuple[bool, str]:
    """Export a binary STL. Failure here (with a successful preview) usually means
    mixed 2D/3D or non-manifold geometry — a real defect worth feeding back."""
    return _run(openscad, scad, stl, ["--export-format=binstl"])
