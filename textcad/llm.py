"""Minimal local-Ollama client (vendored — no external deps, no retail API).

Two calls:
  ollama_generate(prompt, ...)        -> text   (code generation)
  ollama_vision(prompt, image, ...)   -> text   (vision-model judging)

think=False is set on every call: qwen3-family models otherwise emit reasoning
tokens that swallow the response, returning an empty string.
"""
from __future__ import annotations

import base64
import json
import urllib.request
from pathlib import Path

OLLAMA_URL = "http://localhost:11434/api/generate"


def ollama_generate(prompt: str, *, model: str, json_format: bool = False,
                    timeout: int = 240) -> str:
    """Single-shot text generation. Returns the raw `response` string.
    json_format=True asks the model for strict JSON (use with json.loads)."""
    body: dict = {"model": model, "prompt": prompt, "stream": False, "think": False}
    if json_format:
        body["format"] = "json"
    return _post(body, timeout)


def ollama_vision(prompt: str, images: Path | str | list, *, model: str,
                  json_format: bool = True, timeout: int = 180) -> str:
    """Vision generation: send `prompt` plus one or more images (a single path or a
    list of paths, judged together). Returns the `response`."""
    if isinstance(images, (str, Path)):
        images = [images]
    body: dict = {
        "model": model,
        "prompt": prompt,
        "images": [base64.b64encode(Path(im).read_bytes()).decode("ascii") for im in images],
        "stream": False,
    }
    if json_format:
        body["format"] = "json"
    return _post(body, timeout)


def _post(body: dict, timeout: int) -> str:
    req = urllib.request.Request(
        OLLAMA_URL, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace")).get("response", "")
