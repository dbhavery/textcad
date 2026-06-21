"""OpenSCAD code generation: prompts + the LLM call that turns a part description
(or a compile error, or a visual critique) into a complete OpenSCAD program."""
from __future__ import annotations

import re

from .llm import ollama_generate

# A correct through-hole helper is prepended to every generated file. The model only
# has to choose the axis and an in-plane position — it cannot get the error-prone
# rotate()/length/center mechanics wrong, which was the main multi-feature failure.
PRELUDE = """\
// ===textcad:helpers (provided — do NOT redefine these)===
$fn = 64;
// thru_hole(pos, axis, d): SUBTRACT inside difference() to drill a through-hole.
//   axis = "X" | "Y" | "Z" = the drilling direction (a plate's THIN dimension).
//   pos  = [x, y, z], a point on the hole's axis — centre it on the part's two
//          in-plane dimensions. The drill is over-long so it always punches through.
module thru_hole(pos, axis, d) {
  translate(pos) {
    if (axis == "X") rotate([0, 90, 0]) cylinder(h = 1000, d = d, center = true);
    else if (axis == "Y") rotate([90, 0, 0]) cylinder(h = 1000, d = d, center = true);
    else cylinder(h = 1000, d = d, center = true);
  }
}
// ===end helpers===
"""

_PRELUDE_RE = re.compile(
    r"//\s*===textcad:helpers.*?//\s*===end helpers===\n?", re.DOTALL)

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
  thru_hole([0, 0, 0], "Z", inner_d);                // centred through-hole (provided helper)
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
- HOLES — always use the PROVIDED thru_hole(pos, axis, d) helper (already defined at
  the top of the file). SUBTRACT a thru_hole(...) call for each hole inside difference().
  Do NOT write cylinder()/rotate() for holes yourself, and do NOT redefine thru_hole.
  You only choose two things:
    * axis = the plate's THIN dimension (the thickness it is bolted through):
        plate lying flat (thin in Z) -> "Z";  upright plate (thin in X) -> "X";
        plate thin in Y -> "Y".  A bolt hole goes through the FLAT face, never along
        the plate's long or wide dimension.
    * pos  = a point centred on the plate's two LONG dimensions (e.g. middle of the
        height and the width) — never 0, which is an edge and leaves a notch. The
        third coordinate (the through-axis) can be anything inside the plate; the
        drill is over-long.

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
  // Holes via the provided helper: pick axis (the plate's thin dimension) + a centred point.
  thru_hole([leg*0.6, wide/2, t/2], "Z", hole);  // through horizontal plate (flat, thin in z)
  thru_hole([t/2, wide/2, leg*0.6], "X", hole);  // through vertical plate (upright, thin in x)
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
critique. Re-apply the rules: assemble by positioning primitives at explicit corner
coordinates (NOT center=true + rotate), make joining parts OVERLAP into one connected
solid, and drill every hole with the provided thru_hole(pos, axis, d) helper —
choosing axis = the plate's thin dimension and pos = the centre of its two long
dimensions (a missing/edge hole usually means the wrong axis or pos). Keep the parts
of the shape that are already correct; change only what the critique flags. Same hard
rules: OpenSCAD code only, no markdown, no prose, fully parametric, standalone.
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
    code = _PRELUDE_RE.sub("", clean(llm(prompt, model=model, json_format=False, timeout=240)))
    # Prepend the correct helper so the model can't get the hole mechanics wrong.
    return PRELUDE + "\n" + code.lstrip()
