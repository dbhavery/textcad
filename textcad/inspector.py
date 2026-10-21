"""Local vision-model inspector: the link that lets the loop reject valid-but-
WRONG shapes (a round disc passing as a 'hex nut') which compile + STL gates can't.

Judges a SET of orthographic views (top / front / right-side). A single foreshortened
isometric makes small VLMs misread polygons and hides features on vertical faces;
multiple square-on views make both the cross-section and side/bottom features legible.
Local only (Ollama vision API). If the vision model errors or gives no usable
verdict, the inspector reports the check as NOT RUN (approved=None), never as a pass.
"""
from __future__ import annotations

import json
import logging

from .llm import ollama_vision

log = logging.getLogger("textcad.inspector")

_PROMPT = """\
You are a precise CAD reviewer. You are shown orthographic render(s) of ONE part;
this may be a single CONTACT SHEET image with several labelled panels, or separate
images ({labels}). They are the same object seen from different directions. Use
whichever view best shows each feature (the top-down view shows the cross-section /
outline shape; the front and side views show features on the vertical faces such as
legs, side grooves, and holes that enter from a side or the bottom).

The part was generated from this request:

  "{description}"

Judge ONLY the SHAPE and FEATURES, never sizes. You CANNOT measure millimetres from
an image, so you must NOT comment on or reject based on any dimension, hole size,
thickness, or proportion; assume all sizes are correct. Approve as long as:
  (a) the overall form is the right kind of object, AND
  (b) every feature NAMED in the request is present in SOME view (e.g. a hole is
      actually a hole through the part; a "hexagonal" body has a 6-sided outline in
      the top view, not round or rectangular; named slots/grooves/legs/D-shapes are
      visible from the appropriate angle).

Reject ONLY for a wrong gross shape or a missing/wrong named feature, for example a
round disc when a hexagon was asked for, no hole when a hole was requested, a single
flat plate when two perpendicular legs were requested, or a plain round shaft hole
when a D-shaped one was requested. Judge ONLY features that appear in the request
above. Do NOT invent or require any feature (D-shapes, grooves, etc.) that was not
asked for. If the form and all named features are present, APPROVE it. When you
reject, name the specific defect, the feature from the request it concerns, and which
view shows it (or give "" if approved).

Reply ONLY as JSON: {{"approved": true|false, "critique": "..."}}
"""


def make_vlm_inspector(model: str = "qwen2.5vl:7b", timeout: int = 240):
    """Return inspector(views, description) -> (approved, critique) backed by a local
    Ollama vision model. `views` is a list of (label, image_path) tuples (or a single
    path, auto-wrapped).

    `approved` is True (approved), False (rejected, `critique` says why) or None (the
    check did not run: the model errored or its reply had no true/false verdict).
    On None, `critique` holds the reason. The loop treats None as "not checked" and
    reports it in the result; it is never counted as a pass."""

    def inspect(views, description: str) -> tuple[bool, str]:
        # Accept a bare path for backward compatibility.
        if not isinstance(views, (list, tuple)) or (views and not isinstance(views[0], (list, tuple))):
            views = [("view", views)]
        labels = [lbl for lbl, _ in views]
        images = [img for _, img in views]
        prompt = _PROMPT.format(n=len(images), labels=", ".join(labels), description=description)
        try:
            raw = ollama_vision(prompt, images, model=model, json_format=True, timeout=timeout)
            data = json.loads(raw)
            verdict = data.get("approved") if isinstance(data, dict) else None
            if not isinstance(verdict, bool):
                raise ValueError(f"reply has no true/false 'approved' field: {raw[:120]!r}")
            return verdict, str(data.get("critique", "")).strip()
        except Exception as exc:
            log.warning("vlm inspector did not run (%r); vision check not done", exc)
            return None, f"vision check did not run: {exc}"

    return inspect
