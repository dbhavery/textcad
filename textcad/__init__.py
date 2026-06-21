"""textcad — natural-language → OpenSCAD parametric CAD via a local agentic loop.

A clean-room, fully-local pipeline: a local LLM writes parametric OpenSCAD from a
plain-English part description; OpenSCAD (invoked as a tool) renders and exports it;
compile, STL-export, and local vision-model gates feed failures back for repair.
"""
from __future__ import annotations

from .loop import run
from .codegen import generate_scad
from .render import find_openscad, render_png, render_top_png, export_stl
from .inspector import make_vlm_inspector

__version__ = "0.1.0"

__all__ = [
    "run",
    "generate_scad",
    "find_openscad",
    "render_png",
    "render_top_png",
    "export_stl",
    "make_vlm_inspector",
    "__version__",
]
