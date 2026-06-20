#!/usr/bin/env python3
"""inspector — local vision-model judge for textcad renders.

Closes the agentic loop: given the rendered PNG and the original part description,
a local VLM (Ollama qwen2.5vl) decides whether the render actually matches the
request and, if not, returns a concrete critique that textcad feeds back to the
codegen model. This is the link that lets the loop reject valid-but-WRONG shapes
(a round disc passing as a "hex nut") which compile + STL gates cannot catch.

Local only (Ollama vision API). No retail API.

    from inspector import make_vlm_inspector
    result = run(desc, ..., inspector=make_vlm_inspector("qwen2.5vl:7b"))
"""
from __future__ import annotations

import base64
import json
import logging
import urllib.request
from pathlib import Path

log = logging.getLogger("textcad.inspector")

OLLAMA_URL = "http://localhost:11434/api/generate"

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


def _b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def make_vlm_inspector(model: str = "qwen2.5vl:7b", timeout: int = 180):
    """Return an inspector(png_path, description) -> (approved: bool, critique: str)
    backed by a local Ollama vision model. On any error it returns (True, "") so a
    flaky inspector never blocks the pipeline (fail-open)."""

    def inspect(png_path, description: str) -> tuple[bool, str]:
        try:
            payload = json.dumps({
                "model": model,
                "prompt": _PROMPT.format(description=description),
                "images": [_b64(Path(png_path))],
                "stream": False,
                "format": "json",
            }).encode()
            req = urllib.request.Request(
                OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = json.loads(resp.read().decode("utf-8", errors="replace")).get("response", "")
            data = json.loads(raw)
            approved = bool(data.get("approved", False))
            critique = str(data.get("critique", "")).strip()
            return approved, critique
        except Exception as exc:
            log.warning("vlm inspector failed (%r) — failing open (approve)", exc)
            return True, ""

    return inspect
