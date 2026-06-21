"""Local vision-model inspector — the link that lets the loop reject valid-but-
WRONG shapes (a round disc passing as a 'hex nut') which compile + STL gates can't.

Judge a TOP-DOWN orthographic render: a foreshortened isometric makes a 7B VLM
misread polygons. Local only (Ollama vision API), fail-open on error.
"""
from __future__ import annotations

import json
import logging

from .llm import ollama_vision

log = logging.getLogger("textcad.inspector")

_PROMPT = """\
You are a precise CAD reviewer. You are shown a 3D render of a part that was
generated from this request:

  "{description}"

Judge ONLY the SHAPE and FEATURES, never sizes. You CANNOT measure millimetres
from an image, so you must NOT comment on or reject based on any dimension, hole
size, thickness, or proportion — assume all sizes are correct. Approve as long as:
  (a) the overall form is the right kind of object, AND
  (b) every feature NAMED in the request is present (e.g. a hole is actually a
      hole through the part; a "hexagonal" body really has a 6-sided outline, not
      round or rectangular; named slots/grooves/legs are visible).

Reject ONLY for a wrong gross shape or a missing/wrong named feature — for
example a round disc when a hexagon was asked for, or no hole when a hole was
requested. If the form and all named features are present, APPROVE it.
Give a short, concrete critique naming the specific shape/feature defect (or "" if approved).

Reply ONLY as JSON: {{"approved": true|false, "critique": "..."}}
"""


def make_vlm_inspector(model: str = "qwen2.5vl:7b", timeout: int = 180):
    """Return inspector(image_path, description) -> (approved: bool, critique: str)
    backed by a local Ollama vision model. Fails open (approve) on any error so a
    flaky inspector never blocks the pipeline."""

    def inspect(image_path, description: str) -> tuple[bool, str]:
        try:
            raw = ollama_vision(_PROMPT.format(description=description), image_path,
                                model=model, json_format=True, timeout=timeout)
            data = json.loads(raw)
            return bool(data.get("approved", False)), str(data.get("critique", "")).strip()
        except Exception as exc:
            log.warning("vlm inspector failed (%r) — failing open (approve)", exc)
            return True, ""

    return inspect
