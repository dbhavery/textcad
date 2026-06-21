"""Backend resolution + CLI-backend tests (subprocess mocked — no claude/codex needed)."""
import subprocess

import pytest

import textcad.backends as b
from textcad.backends import resolve, claude_backend, DEFAULT_MODEL
from textcad.llm import ollama_generate


def test_resolve_returns_callables():
    assert resolve("ollama") is ollama_generate
    assert callable(resolve("claude"))
    assert callable(resolve("codex"))


def test_resolve_unknown_raises():
    with pytest.raises(ValueError):
        resolve("gpt9")


def test_default_models():
    assert DEFAULT_MODEL["ollama"] == "qwen2.5-coder:32b"
    assert DEFAULT_MODEL["claude"] is None


def test_claude_backend_invokes_cli(monkeypatch):
    calls = {}

    def fake_which(name):
        return f"/usr/bin/{name}"

    def fake_run(argv, **kw):
        calls["argv"] = argv
        calls["cwd"] = kw.get("cwd")
        return subprocess.CompletedProcess(argv, 0, stdout="cube(1);", stderr="")

    monkeypatch.setattr(b.shutil, "which", fake_which)
    monkeypatch.setattr(b.subprocess, "run", fake_run)
    out = claude_backend("make a cube", model="sonnet")
    assert out == "cube(1);"
    assert calls["argv"][:1] == ["/usr/bin/claude"]
    assert "--model" in calls["argv"] and "sonnet" in calls["argv"]
    assert "-p" in calls["argv"]
    assert calls["cwd"] is not None  # ran in a neutral temp dir


def test_claude_backend_missing_cli_raises(monkeypatch):
    monkeypatch.setattr(b.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError):
        claude_backend("x")


def test_claude_backend_nonzero_exit_raises(monkeypatch):
    monkeypatch.setattr(b.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(b.subprocess, "run",
                        lambda argv, **kw: subprocess.CompletedProcess(argv, 1, "", "boom"))
    with pytest.raises(RuntimeError):
        claude_backend("x")
