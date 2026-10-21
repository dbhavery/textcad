"""Inspector tests: the Ollama vision call is monkeypatched."""
import textcad.inspector as inspector_mod
from textcad.inspector import make_vlm_inspector


def test_parses_approval_json(monkeypatch):
    monkeypatch.setattr(inspector_mod, "ollama_vision",
                        lambda *a, **k: '{"approved": true, "critique": ""}')
    approved, crit = make_vlm_inspector()("img.png", "a hex nut")
    assert approved is True
    assert crit == ""


def test_parses_rejection_json(monkeypatch):
    monkeypatch.setattr(inspector_mod, "ollama_vision",
                        lambda *a, **k: '{"approved": false, "critique": "it is round, not hexagonal"}')
    approved, crit = make_vlm_inspector()("img.png", "a hex nut")
    assert approved is False
    assert "round" in crit


def test_error_is_reported_as_not_checked(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("ollama down")
    monkeypatch.setattr(inspector_mod, "ollama_vision", boom)
    approved, crit = make_vlm_inspector()("img.png", "a hex nut")
    assert approved is None  # not checked: never reported as a pass
    assert "did not run" in crit
    assert "ollama down" in crit


def test_malformed_json_is_reported_as_not_checked(monkeypatch):
    monkeypatch.setattr(inspector_mod, "ollama_vision", lambda *a, **k: "not json at all")
    approved, crit = make_vlm_inspector()("img.png", "a hex nut")
    assert approved is None
    assert "did not run" in crit


def test_reply_without_approved_field_is_not_checked(monkeypatch):
    monkeypatch.setattr(inspector_mod, "ollama_vision", lambda *a, **k: '{"critique": "hmm"}')
    approved, crit = make_vlm_inspector()("img.png", "a hex nut")
    assert approved is None
    assert "did not run" in crit


def test_multiview_passes_all_images_and_labels(monkeypatch):
    seen = {}

    def fake(prompt, images, *, model, json_format, timeout):
        seen["prompt"] = prompt
        seen["n"] = len(images)
        return '{"approved": true, "critique": ""}'

    monkeypatch.setattr(inspector_mod, "ollama_vision", fake)
    views = [("top-down", "t.png"), ("front", "f.png"), ("right-side", "r.png")]
    approved, _ = make_vlm_inspector()(views, "a bracket")
    assert approved is True
    assert seen["n"] == 3
    assert "top-down, front, right-side" in seen["prompt"]
