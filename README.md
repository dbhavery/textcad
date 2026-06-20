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
python textcad.py "a hexagonal nut, 10mm across flats, 5mm thick, 5mm center hole"
python textcad.py "a coffee mug with a handle" --name mug --iters 4
```

Outputs land in `out/<name>.scad`, `out/<name>.png`, `out/<name>.stl`.

## Requirements

- OpenSCAD on PATH or in `C:/Program Files/OpenSCAD/` (`winget install OpenSCAD.OpenSCAD`)
- Ollama running with the codegen model pulled (`ollama pull qwen3:14b`)
- `local-llm-synthesis` skill at `C:/Users/dbhav/Projects/Skills/local-llm-synthesis`

## Status

Proof-of-concept. Demonstrates the codegen → render → compile-fix loop end to end.
Not a product. Next steps if pursued: a local VLM inspector to automate visual
critique, multi-view screenshots, and a parameter-slider UI over the named vars.
