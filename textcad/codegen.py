"""OpenSCAD code generation: prompts + the LLM call that turns a part description
(or a compile error, or a visual critique) into a complete OpenSCAD program."""
from __future__ import annotations

import re

from .llm import ollama_generate

# The system prompt carries a worked difference() example — small local models
# omit difference() without one, producing solids with no holes.
SYSTEM = """\
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

BUILDING MULTI-PART SHAPES — placement rules (follow strictly):
- Assemble shapes by positioning each primitive at EXPLICIT coordinates anchored at
  a CORNER. Do NOT use center=true when parts must line up, and do NOT use rotate()
  to PLACE a part — size and position cubes instead (rotate() is only for orienting
  a hole). center=true + rotate + translate is the #1 cause of disconnected, gappy
  geometry.
- Where two parts join they must OVERLAP (share a volume), so the result is ONE
  connected solid. Mentally check the coordinate ranges actually touch — a gap means
  two loose pieces, not one part.
- HOLE ORIENTATION (critical): a bolt / mounting hole passes through the FLAT face of
  a plate, i.e. along the plate's THINNEST dimension (its thickness), so the plate can
  bolt flat against a surface. NEVER run a bolt hole along a plate's long or wide
  dimension. Pick the axis by which dimension is the thickness:
    * plate lying flat (thin in Z)  -> hole is the Z axis, no rotate()
    * upright plate (thin in X)     -> hole is the X axis, rotate([0, 90, 0])
    * plate thin in Y               -> hole is the Y axis, rotate([90, 0, 0])
  "Centred in the leg" means centred across the leg's two LONG dimensions, drilling
  through the short (thickness) one. Give BOTH in-plane coordinates a value in the
  MIDDLE of the leg (e.g. height*0.5 and width*0.5) — never 0, which is an edge and
  leaves a notch instead of a hole. Mnemonic: rotate([0,90,0]) makes a cylinder point
  along X; rotate([90,0,0]) makes it point along Y; no rotate = along Z.
- For the through-direction, do NOT compute the wall thickness. Make the drill cylinder
  MUCH LONGER than the part and centered (h = 200, center = true); an over-long centered
  cylinder punches fully through wherever the material is. You then only need the two
  in-plane coordinates and the correct axis (above), and to keep it clear of other parts.

Worked example 2 — an L-bracket: two perpendicular plates meeting at a corner,
positioned by corners and overlapping at the joint (one connected solid), with a
bolt hole through each plate from the correct direction:
---
$fn = 64;
leg = 40; wide = 30; t = 4; hole = 5;
difference() {
  union() {
    cube([t,   wide, leg]);  // vertical plate: thin in x, full height in z
    cube([leg, wide, t  ]);  // horizontal plate: long in x, thin in z; shares the bottom corner
  }
  // Over-long centered drills: only the two in-plane coords matter; the long axis
  // punches all the way through wherever the plate is.
  translate([leg*0.6, wide/2, 0]) cylinder(h = 200, d = hole, center = true);                  // hole down through horizontal plate (z axis)
  translate([0, wide/2, leg*0.6]) rotate([0, 90, 0]) cylinder(h = 200, d = hole, center = true); // hole through vertical plate (x axis)
}
---

PLAN FIRST, IN COMMENTS. Before the difference(), write a short `// PLAN:` comment
block working the geometry out numerically — the x/y/z coordinate box of each solid
(check the boxes OVERLAP so the part is connected), and for each hole its axis
(X/Y/Z per the orientation rule), the two in-plane coords it is centred on, and which
part it passes through. Then write code that matches the plan. Comments are valid
OpenSCAD, so this keeps the output "code only".

Now build the requested part with the same rigor.
"""

FIX = """\
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

CRITIQUE = """\
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
critique. Re-apply the placement rules: assemble by positioning primitives at
explicit corner coordinates (NOT center=true + rotate), make joining parts OVERLAP
into one connected solid, and put each hole's axis through the CENTRE of the face
it enters so it passes through solid material. Keep the parts of the shape that are
already correct; change only what the critique flags. Same hard rules: OpenSCAD code
only, no markdown, no prose, fully parametric, standalone (no libraries).
"""

_FENCE = re.compile(r"^```[a-zA-Z]*\n|\n```$", re.MULTILINE)


def clean(code: str) -> str:
    """Strip stray markdown fences / a leading 'openscad' the model may emit."""
    code = _FENCE.sub("", code).strip()
    if code.lower().startswith("openscad\n"):
        code = code.split("\n", 1)[1]
    return code.strip() + "\n"


def generate_scad(description: str, *, model: str, prior_code: str | None = None,
                  error: str | None = None, critique: str | None = None,
                  llm=ollama_generate) -> str:
    """Generate OpenSCAD code: fresh, a compile-fix, or a fix for a visual critique.
    `llm(prompt, model=, json_format=)` is injectable for testing."""
    if prior_code and error:
        prompt = SYSTEM + "\n\n" + FIX.format(error=error[:1500], code=prior_code)
    elif prior_code and critique:
        prompt = SYSTEM + "\n\n" + CRITIQUE.format(critique=critique[:1500], code=prior_code)
    else:
        prompt = SYSTEM + f"\n\nDescribe-to-build: {description}\n"
    return clean(llm(prompt, model=model, json_format=False, timeout=240))
