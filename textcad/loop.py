"""The agentic loop: generate -> render -> gate -> feed failures back -> repeat."""
from __future__ import annotations

from pathlib import Path

from .codegen import generate_scad
from .render import find_openscad, render_png, render_views, make_contact_sheet, export_stl


def run(description: str, *, name: str = "part", model: str = "qwen2.5-coder:32b",
        iters: int = 3, inspector=None, out_dir: str | Path = "out") -> dict:
    """Generate an OpenSCAD part from `description`, iterating up to `iters` times.

    Each iteration runs three gates; a failure at any gate feeds specific text back
    to the next generation:
      1. compile     — OpenSCAD must render a preview (stderr feeds back)
      2. STL export  — must produce a non-empty STL (mixed-2D/3D / non-manifold feeds back)
      3. inspector   — optional (image, description) -> (approved, critique);
                       a failing visual critique feeds back

    Returns a dict with paths (scad/png/stl), attempt count, and per-attempt history.
    With no inspector, the first compile-and-exportable part wins.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    openscad = find_openscad()
    if not openscad:
        return {"error": "OpenSCAD binary not found (set $TEXTCAD_OPENSCAD, "
                         "bundle tools/openscad-*/, or install it)."}

    scad = out / f"{name}.scad"
    png = out / f"{name}.png"
    stl = out / f"{name}.stl"
    code, error, critique = None, None, None
    history: list[dict] = []

    for attempt in range(1, iters + 1):
        code = generate_scad(description, model=model, prior_code=code,
                             error=error, critique=critique)
        scad.write_text(code, encoding="utf-8")
        critique = None

        ok, error = render_png(openscad, scad, png)
        if not ok:
            history.append({"attempt": attempt, "compiled": False, "feedback": error[:200]})
            print(f"[attempt {attempt}] compiled=False  error={error[:140]!r}")
            continue

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

        if inspector is not None:
            views = render_views(openscad, scad, out / name)  # top + front + side
            sheet = make_contact_sheet(views, out / f"{name}_sheet.png") if views else None
            if sheet:
                viewset = [("orthographic contact sheet (top-down, front, right-side panels)", sheet)]
            else:
                viewset = views or [("iso", png)]  # Pillow missing / no views: fall back
            approved, crit = inspector(viewset, description)
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
