#!/usr/bin/env python3
"""textcad — clean-room text->OpenSCAD agentic proof.

Demonstrates the pattern (NOT the code) borrowed conceptually from CADAM:
    natural-language part description
        -> LLM writes parametric OpenSCAD code        (local Ollama qwen3:14b)
        -> render to PNG + export STL                 (OpenSCAD CLI, used as a tool)
        -> on compile error, feed stderr back, retry  (the agentic loop)
        -> a vision inspector critiques the render     (pluggable; see --inspect)

Nothing here is copied from CADAM (GPLv3). The OpenSCAD *binary* is invoked as an
external tool, which does not create a derivative work. LLM calls reuse Don's
`local-llm-synthesis` skill (local Ollama, no retail API).

Usage:
    python textcad.py "a hexagonal nut, 10mm across flats, 5mm thick, with a 5mm hole"
    python textcad.py "a coffee mug with a handle" --iters 4 --name mug
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# --- reuse the local-llm-synthesis skill for model calls -------------------- #
sys.path.insert(0, r"C:/Users/dbhav/Projects/Skills/local-llm-synthesis")
from ollama_synth import ollama_generate  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"

# OpenSCAD writes the model code; we keep the prompt tight and deterministic.
_SYSTEM = """\
You are an expert OpenSCAD engineer. Given a plain-English description of a physical
part, output a COMPLETE, COMPILABLE OpenSCAD program that models it.

Hard rules:
1. Output ONLY OpenSCAD code. No markdown fences, no prose, no explanation.
2. Put every dimension in a named parameter at the TOP of the file (mm units),
   each with a short trailing comment, so the part is fully parametric.
3. Use $fn = 64; near the top for smooth curved surfaces.
4. The model must be a single connected solid (use union()/difference()/hull()),
   centered on the origin, resting sensibly (bottom near z=0 where natural).
5. Keep dimensions realistic for a hand-held part (single-digit to ~150 mm).
6. Do NOT call any external library (no `use <...>` / `include <...>`); only
   built-in primitives and transforms so it compiles standalone.
7. To make a HOLE or remove material you MUST use difference() — the thing to
   remove goes INSIDE difference() after the solid. Never just place a cylinder
   next to the body and expect a hole; that only ADDS material.

Worked example — a washer (disc with a centered through-hole), showing the
correct difference() pattern. Follow this structure:
---
$fn = 64;
outer_d = 20;   // outer diameter, mm
inner_d = 8;    // hole diameter, mm
thick   = 3;    // thickness, mm
difference() {
  cylinder(h = thick, d = outer_d, center = true);   // solid body
  cylinder(h = thick + 1, d = inner_d, center = true); // hole: SUBTRACTED, taller so it punches through
}
---
Now build the requested part with the same rigor.
"""

_FIX = """\
The previous OpenSCAD code FAILED to compile. Here is the compiler error:
---
{error}
---
Here is the code that failed:
---
{code}
---
Return a corrected COMPLETE OpenSCAD program that fixes the error. Same hard rules:
OpenSCAD code only, no markdown, no prose, fully parametric, standalone (no libraries).
"""

# Visual-inspector feedback: the code compiled, but the *rendered shape* is wrong.
# This is the half a compiler can never catch (no difference(), wrong primitive, etc.).
_CRITIQUE = """\
The previous OpenSCAD code compiled, but a visual inspection of the render shows
the geometry is WRONG. Inspector critique:
---
{critique}
---
Here is the code to correct:
---
{code}
---
Return a COMPLETE corrected OpenSCAD program that addresses every point in the
critique. Same hard rules: OpenSCAD code only, no markdown, no prose, fully
parametric, standalone (no libraries).
"""

_FENCE = re.compile(r"^```[a-zA-Z]*\n|\n```$", re.MULTILINE)


def _clean(code: str) -> str:
    """Strip any stray markdown fences / leading 'openscad' the model may emit."""
    code = _FENCE.sub("", code).strip()
    if code.lower().startswith("openscad\n"):
        code = code.split("\n", 1)[1]
    return code.strip() + "\n"


def find_openscad() -> str | None:
    """Locate the OpenSCAD binary across PATH and standard Windows install dirs."""
    import shutil
    for name in ("openscad", "openscad.exe", "openscad.com"):
        p = shutil.which(name)
        if p:
            return p
    candidates = [
        # bundled portable copy (preferred — no install/admin needed)
        *HERE.glob("tools/openscad-*/openscad.exe"),
        Path(r"C:/Program Files/OpenSCAD/openscad.exe"),
        Path(r"C:/Program Files/OpenSCAD (Nightly)/openscad.exe"),
        Path(r"C:/Program Files/OpenSCAD/openscad.com"),
    ]
    for c in candidates:
        if Path(c).exists():
            return str(c)
    return None


def generate_scad(description: str, *, model: str, prior_code: str | None = None,
                  error: str | None = None, critique: str | None = None) -> str:
    """Ask the local LLM for OpenSCAD code: fresh, a compile-fix, or a fix that
    addresses a visual inspector's critique of the render."""
    if prior_code and error:
        prompt = _SYSTEM + "\n\n" + _FIX.format(error=error[:1500], code=prior_code)
    elif prior_code and critique:
        prompt = _SYSTEM + "\n\n" + _CRITIQUE.format(critique=critique[:1500], code=prior_code)
    else:
        prompt = _SYSTEM + f"\n\nDescribe-to-build: {description}\n"
    raw = ollama_generate(prompt, model=model, json_format=False, timeout=240)
    return _clean(raw)


def _run_openscad(openscad: str, scad: Path, out: Path, extra: list[str]) -> tuple[bool, str]:
    cmd = [openscad, "-o", str(out), *extra, str(scad)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    ok = proc.returncode == 0 and out.exists() and out.stat().st_size > 0
    return ok, (proc.stderr or proc.stdout or "").strip()


def render_png(openscad: str, scad: Path, png: Path) -> tuple[bool, str]:
    return _run_openscad(openscad, scad, png, [
        "--autocenter", "--viewall", "--imgsize=1024,768",
        "--colorscheme=Tomorrow", "--render",
    ])


def render_top_png(openscad: str, scad: Path, png: Path) -> tuple[bool, str]:
    """Straight top-down orthographic view. A foreshortened isometric makes small
    vision models misread polygons (a hexagon reads as 'rectangular'); a top view
    makes the cross-section unambiguous for the inspector. (CADAM renders several
    orthographic views for the same reason.)"""
    return _run_openscad(openscad, scad, png, [
        "--projection=o", "--camera=0,0,100,0,0,0", "--viewall", "--autocenter",
        "--imgsize=1024,768", "--colorscheme=Tomorrow", "--render",
    ])


def export_stl(openscad: str, scad: Path, stl: Path) -> tuple[bool, str]:
    return _run_openscad(openscad, scad, stl, ["--export-format=binstl"])


def run(description: str, *, name: str, model: str, iters: int, inspector=None) -> dict:
    """Agentic loop. Each iteration: generate -> render. A compile error feeds the
    `stderr` back. If it compiles and an `inspector(png, description)->(ok, critique)`
    is supplied, a failing visual critique feeds back instead. Without an inspector,
    the first clean compile wins (compile-only mode)."""
    OUT.mkdir(parents=True, exist_ok=True)
    openscad = find_openscad()
    if not openscad:
        return {"error": "OpenSCAD binary not found (bundle tools/openscad-*/ or install)."}

    scad = OUT / f"{name}.scad"
    png = OUT / f"{name}.png"
    stl = OUT / f"{name}.stl"
    code, error, critique = None, None, None
    history: list[dict] = []

    for attempt in range(1, iters + 1):
        code = generate_scad(description, model=model, prior_code=code,
                             error=error, critique=critique)
        scad.write_text(code, encoding="utf-8")
        ok, error = render_png(openscad, scad, png)
        critique = None
        if not ok:
            history.append({"attempt": attempt, "compiled": False, "feedback": error[:200]})
            print(f"[attempt {attempt}] compiled=False  error={error[:140]!r}")
            continue

        # Validity gate: it must also export a non-empty STL. A part that renders
        # but won't export is usually mixed 2D/3D geometry or a non-manifold/empty
        # solid — a real defect, so feed it back like a compile error.
        stl_ok, stl_err = export_stl(openscad, scad, stl)
        if not stl_ok:
            error = ("The code rendered a preview but STL export FAILED — this usually "
                     "means the geometry mixes 2D and 3D objects (e.g. a bare polygon()/"
                     "circle() not wrapped in linear_extrude alongside 3D solids), or the "
                     "result is empty/non-manifold. Make the whole model a single 3D solid. "
                     f"Exporter said: {stl_err}")
            history.append({"attempt": attempt, "compiled": True, "stl": False,
                            "feedback": error[:200]})
            print(f"[attempt {attempt}] compiled=True but STL export FAILED — feeding back")
            continue

        # Compiled and exports — run the visual inspector if one is wired in.
        if inspector is not None:
            top = OUT / f"{name}_top.png"
            tok, _ = render_top_png(openscad, scad, top)
            view = top if tok else png  # top-down reads polygons unambiguously
            approved, crit = inspector(view, description)
            history.append({"attempt": attempt, "compiled": True, "stl": True,
                            "approved": approved, "feedback": "" if approved else crit[:200]})
            print(f"[attempt {attempt}] compiled=True stl=True  inspector_approved={approved}"
                  + ("" if approved else f"  critique={crit[:120]!r}"))
            if not approved:
                critique = crit
                continue
        else:
            history.append({"attempt": attempt, "compiled": True, "stl": True, "approved": None})
            print(f"[attempt {attempt}] compiled=True stl=True (no inspector — accepting)")

        return {"openscad": openscad, "description": description, "scad": str(scad),
                "png": str(png), "stl": str(stl), "attempts": attempt, "history": history}

    return {"openscad": openscad, "description": description, "scad": str(scad),
            "png": str(png), "stl": None, "attempts": iters, "history": history,
            "error": "did not converge within iteration budget"}


def main() -> None:
    ap = argparse.ArgumentParser(description="text -> OpenSCAD agentic proof")
    ap.add_argument("description", help="plain-English part description")
    ap.add_argument("--name", default="part", help="output basename (out/<name>.scad|png|stl)")
    ap.add_argument("--model", default="qwen3:14b", help="Ollama model for codegen")
    ap.add_argument("--iters", type=int, default=3, help="max generate/fix attempts")
    ap.add_argument("--inspect", nargs="?", const="qwen2.5vl:7b", default=None,
                    metavar="VLM_MODEL",
                    help="enable the local vision-model inspector (default qwen2.5vl:7b)")
    args = ap.parse_args()

    inspector = None
    if args.inspect:
        from inspector import make_vlm_inspector
        inspector = make_vlm_inspector(args.inspect)
    result = run(args.description, name=args.name, model=args.model,
                 iters=args.iters, inspector=inspector)
    print("\n=== RESULT ===")
    for k in ("description", "attempts", "scad", "png", "stl", "error"):
        if result.get(k) not in (None, ""):
            print(f"{k:12}: {result[k]}")


if __name__ == "__main__":
    main()
