# textcad — text → OpenSCAD agentic proof

A **clean-room** demonstration of the core idea behind CADAM, built from scratch
so it carries **none of CADAM's GPLv3 obligations**.

## The idea (clean-room, not the code)

```
"a hex nut, 10mm across flats, 5mm hole"
   → local LLM writes parametric OpenSCAD code      (Ollama qwen3:14b)
   → OpenSCAD CLI renders a PNG + exports an STL     (binary used as a tool)
   → if it fails to compile, the error is fed back   ← the agentic loop
     and the model rewrites until it compiles
   → a vision inspector critiques the render          (pluggable, see below)
```

Only the *pattern* is borrowed (LLM writes code → render → inspect → iterate).
Every line here is original. The OpenSCAD binary is **invoked as an external
tool**, which does not create a derivative work — so nothing built on top of this
inherits GPL.

## Why this design

- **Local codegen, no retail API** — model calls go through Don's
  `local-llm-synthesis` skill (Ollama on `localhost:11434`), honoring the
  bare-metal-inference rule. Swap `--model` for any pulled Ollama model.
- **OpenSCAD as the geometry kernel** — parametric, scriptable, headless-renderable
  from the CLI; no WASM/Three.js stack needed for a proof.
- **Compile-error feedback is the agent** — the highest-value, vision-free half of
  CADAM's loop. The model gets the real compiler `stderr` and fixes its own code.
- **Inspector is pluggable** — there is no local vision model installed
  (`ollama list` has qwen3 + gemma4 + embeddings, no llava/qwen-vl), so visual
  critique is done out-of-band for now (render the PNG, look at it). Drop in a
  local VLM later to close the loop fully autonomously.

## Usage

```bash
# compile-only loop (fast, accepts first valid-and-exportable part)
python textcad.py "a hexagonal nut, 16mm across flats, 6mm thick, 8mm center hole" --model qwen2.5-coder:32b

# full closed loop: add the local vision-model inspector
python textcad.py "a hexagonal nut, 16mm across flats, 6mm thick, 8mm center hole" \
    --model qwen2.5-coder:32b --inspect qwen2.5vl:7b --iters 4

# compare codegen models on a fixed part set
python bench.py qwen2.5-coder:32b
```

Outputs land in `out/<name>.scad`, `out/<name>.png` (iso), `out/<name>_top.png`
(top-down, used by the inspector), `out/<name>.stl`.

## Gates (what the loop checks each iteration)

1. **Compile** — OpenSCAD must render a preview; `stderr` feeds back on failure.
2. **STL export** — must produce a non-empty STL; catches mixed 2D/3D and
   non-manifold geometry that previews fine but won't export.
3. **Visual inspector** (optional, `--inspect`) — a local VLM judges a **top-down
   orthographic** render against the request and rejects valid-but-wrong shapes
   (e.g. a round disc when a hexagon was asked for). Top-down is essential: a
   foreshortened isometric makes a 7B VLM misread a hexagon as "rectangular".

## Requirements

- OpenSCAD — bundled portable copy in `tools/openscad-*/` (auto-detected), or installed.
- Ollama running with:
  - a codegen model — `ollama pull qwen2.5-coder:32b` (best tested; `qwen3:14b` weaker)
  - a vision model for `--inspect` — `ollama pull qwen2.5vl:7b`
- `local-llm-synthesis` skill at `C:/Users/dbhav/Projects/Skills/local-llm-synthesis`

## Status — closed loop WORKS, fully local

Verified end-to-end: text -> qwen2.5-coder:32b writes OpenSCAD -> render iso+top ->
compile + STL + VLM gates -> critique feeds back -> regenerate. On a hex nut the
loop self-corrected a wrong shape on attempt 1 to an APPROVED correct part on
attempt 2 — autonomous, no retail API.

Model findings: qwen2.5-coder:32b handles single-feature parts (nut, washer) but
is non-deterministic and still struggles with multi-feature parts (perpendicular
legs, D-profile shafts, finger grooves). qwen2.5vl:7b is a reliable shape/feature
judge only on top-down ortho views.

Not a product. Natural next steps: multi-view inspection (front+side, not just
top), a stronger/larger VLM for complex parts, and a parameter-slider UI over the
named OpenSCAD vars.
