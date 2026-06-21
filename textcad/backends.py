"""Codegen backends. The default is local Ollama; optionally a frontier model can
generate the OpenSCAD via a subscription CLI (Claude Code or Codex) — no API key.

Frontier models place multi-feature geometry (e.g. a bolt hole through each leg of
an L-bracket, on the correct axis) correctly zero-shot, where the small local coder
needs heavy prompting and still slips. textcad stays local-FIRST: you opt in with
`--backend claude` / `--backend codex`.

CLI backends are run from a NEUTRAL temp dir so the agent does not inherit the
current project's context (CLAUDE.md, skills, etc.), which otherwise pollutes the
output. Each backend matches the llm() signature so it drops into generate_scad.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile

from .llm import ollama_generate


def _run_cli(argv: list[str], timeout: int) -> str:
    exe = shutil.which(argv[0])
    if not exe:
        raise RuntimeError(f"{argv[0]!r} not found on PATH — is it installed and logged in?")
    with tempfile.TemporaryDirectory() as neutral:  # avoid project-context leakage
        proc = subprocess.run([exe, *argv[1:]], cwd=neutral, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"{argv[0]} exited {proc.returncode}: {(proc.stderr or '')[:300]}")
    out = (proc.stdout or "").strip()
    if not out:
        raise RuntimeError(f"{argv[0]} returned empty output")
    return out


def claude_backend(prompt: str, *, model: str | None = None,
                   json_format: bool = False, timeout: int = 300) -> str:
    """Generate via the Claude Code CLI (`claude -p`). Runs on the Max subscription,
    not the Anthropic API. `model` maps to --model (e.g. 'sonnet', 'opus')."""
    argv = ["claude"] + (["--model", model] if model else []) + ["-p", prompt]
    return _run_cli(argv, timeout)


def codex_backend(prompt: str, *, model: str | None = None,
                  json_format: bool = False, timeout: int = 300) -> str:
    """Generate via the Codex CLI (`codex exec`). Subscription, no API key."""
    argv = ["codex", "exec"] + (["-m", model] if model else []) + [prompt]
    return _run_cli(argv, timeout)


BACKENDS = {
    "ollama": ollama_generate,
    "claude": claude_backend,
    "codex": codex_backend,
}

# Sensible default model per backend (None = let the CLI/backend pick its own).
DEFAULT_MODEL = {
    "ollama": "qwen2.5-coder:32b",
    "claude": None,
    "codex": None,
}


def resolve(name: str):
    if name not in BACKENDS:
        raise ValueError(f"unknown backend {name!r}; choose from {sorted(BACKENDS)}")
    return BACKENDS[name]
