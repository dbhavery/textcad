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
critique. Same hard rules: OpenSCAD code only, no markdown, no prose, fully
parametric, standalone (no libraries).
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
