"""Loop gate-logic tests: OpenSCAD and Ollama are fully monkeypatched, so these
run in CI with no binaries and no GPU."""
import textcad.loop as loop
from textcad.loop import run


def _patch(monkeypatch, *, render, export, gen=lambda *a, **k: "cube(1);\n", views=None):
    monkeypatch.setattr(loop, "find_openscad", lambda: "openscad")
    monkeypatch.setattr(loop, "generate_scad", gen)
    monkeypatch.setattr(loop, "render_png", render)
    monkeypatch.setattr(loop, "export_stl", export)
    monkeypatch.setattr(loop, "render_views",
                        views or (lambda o, s, base: [("top-down", base)]))
    monkeypatch.setattr(loop, "make_contact_sheet", lambda vs, out, **k: out)


def test_accepts_first_valid_part(monkeypatch, tmp_path):
    _patch(monkeypatch, render=lambda o, s, p: (True, ""), export=lambda o, s, p: (True, ""))
    res = run("a cube", name="t", iters=3, out_dir=tmp_path)
    assert res["attempts"] == 1
    assert res["stl"] and "error" not in res


def test_compile_error_feeds_back_then_succeeds(monkeypatch, tmp_path):
    calls = {"n": 0}

    def render(o, s, p):
        calls["n"] += 1
        return (calls["n"] > 1, "" if calls["n"] > 1 else "Parser error")

    _patch(monkeypatch, render=render, export=lambda o, s, p: (True, ""))
    res = run("a cube", name="t", iters=3, out_dir=tmp_path)
    assert res["attempts"] == 2
    assert res["history"][0]["compiled"] is False
    assert "Parser error" in res["history"][0]["feedback"]


def test_stl_export_failure_is_gated_and_feeds_back(monkeypatch, tmp_path):
    calls = {"n": 0}

    def export(o, s, p):
        calls["n"] += 1
        return (calls["n"] > 1, "" if calls["n"] > 1 else "Top level object is empty")

    _patch(monkeypatch, render=lambda o, s, p: (True, ""), export=export)
    res = run("a cube", name="t", iters=3, out_dir=tmp_path)
    assert res["attempts"] == 2
    assert res["history"][0]["stl"] is False
    assert "STL export FAILED" in res["history"][0]["feedback"]


def test_inspector_rejects_then_approves(monkeypatch, tmp_path):
    verdicts = [(False, "not hexagonal"), (True, "")]
    inspector = lambda img, desc: verdicts.pop(0)
    _patch(monkeypatch, render=lambda o, s, p: (True, ""), export=lambda o, s, p: (True, ""))
    res = run("a hex nut", name="t", iters=3, inspector=inspector, out_dir=tmp_path)
    assert res["attempts"] == 2
    assert res["history"][0]["approved"] is False
    assert res["history"][1]["approved"] is True


def test_errored_vision_check_is_not_reported_as_passed(monkeypatch, tmp_path):
    """A vision model that errors must not count as a pass. The part is accepted on
    the compile and STL-export gates only, and the result says the vision check
    did not run."""
    inspector = lambda img, desc: (None, "vision check did not run: ollama down")
    _patch(monkeypatch, render=lambda o, s, p: (True, ""), export=lambda o, s, p: (True, ""))
    res = run("a hex nut", name="t", iters=3, inspector=inspector, out_dir=tmp_path)
    assert res["attempts"] == 1
    assert res["stl"] and "error" not in res
    assert res["vision_check"] == "not run"
    assert res["history"][0]["approved"] is None
    assert "ollama down" in res["history"][0]["feedback"]


def test_vision_check_status_when_passed_and_when_off(monkeypatch, tmp_path):
    _patch(monkeypatch, render=lambda o, s, p: (True, ""), export=lambda o, s, p: (True, ""))
    passed = run("a cube", name="a", iters=1, inspector=lambda i, d: (True, ""),
                 out_dir=tmp_path)
    assert passed["vision_check"] == "passed"
    off = run("a cube", name="b", iters=1, out_dir=tmp_path)
    assert off["vision_check"] == "off"


def test_no_convergence_within_budget(monkeypatch, tmp_path):
    _patch(monkeypatch, render=lambda o, s, p: (False, "always broken"),
           export=lambda o, s, p: (True, ""))
    res = run("a cube", name="t", iters=2, out_dir=tmp_path)
    assert res["stl"] is None
    assert "did not converge" in res["error"]
    assert len(res["history"]) == 2


def test_missing_openscad_returns_error(monkeypatch, tmp_path):
    monkeypatch.setattr(loop, "find_openscad", lambda: None)
    res = run("a cube", name="t", out_dir=tmp_path)
    assert "OpenSCAD binary not found" in res["error"]
