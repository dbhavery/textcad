"""Codegen unit tests — no Ollama required (LLM backend is injected)."""
from textcad.codegen import clean, generate_scad


def test_clean_strips_markdown_fences():
    assert clean("```openscad\ncube(1);\n```") == "cube(1);\n"
    assert clean("```\ncube(2);\n```") == "cube(2);\n"


def test_clean_plain_code_gets_trailing_newline():
    assert clean("cube(3);") == "cube(3);\n"


def test_clean_strips_leading_openscad_word():
    assert clean("openscad\ncube(4);") == "cube(4);\n"


def _capturing_llm(store):
    def llm(prompt, *, model, json_format, timeout):
        store["prompt"] = prompt
        store["model"] = model
        return "cube(1);"
    return llm


def test_fresh_prompt_contains_description():
    store = {}
    generate_scad("a 10mm cube", model="m", llm=_capturing_llm(store))
    assert "Describe-to-build: a 10mm cube" in store["prompt"]
    assert store["model"] == "m"


def test_compile_fix_branch_includes_error_and_prior_code():
    store = {}
    generate_scad("x", model="m", prior_code="OLDCODE", error="syntax ERR",
                  llm=_capturing_llm(store))
    assert "FAILED to compile" in store["prompt"]
    assert "syntax ERR" in store["prompt"]
    assert "OLDCODE" in store["prompt"]


def test_critique_branch_includes_critique():
    store = {}
    generate_scad("x", model="m", prior_code="OLDCODE", critique="not hexagonal",
                  llm=_capturing_llm(store))
    assert "visual inspection" in store["prompt"]
    assert "not hexagonal" in store["prompt"]
