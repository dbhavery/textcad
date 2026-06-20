#!/usr/bin/env python3
"""bench — run a fixed set of parts through textcad for a given model.

Lets us compare codegen models on identical prompts:
    python bench.py qwen3:14b
    python bench.py qwen2.5-coder:32b

Writes out/<safe_model>__<part>.{scad,png,stl} and prints a compile summary.
Visual correctness is judged by a human/VLM looking at the PNGs (no local VLM yet).
"""
from __future__ import annotations

import sys

import textcad as T

# Representative parts spanning difference(), regular polygons, fillets, handles.
PARTS = {
    "hexnut": "a hexagonal nut, 16mm across the flats, 6mm thick, with an 8mm diameter through hole in the center",
    "washer": "a flat washer, 24mm outer diameter, 10mm inner hole, 2.5mm thick",
    "lbracket": "an L-shaped mounting bracket, 40mm x 40mm legs, 4mm wall thickness, 30mm wide, with a 5mm bolt hole centered in each leg",
    "knob": "a cylindrical control knob 30mm diameter and 20mm tall, with a 6mm D-shaped shaft hole in the bottom and shallow finger grooves around the side",
}


def main() -> None:
    model = sys.argv[1] if len(sys.argv) > 1 else "qwen3:14b"
    iters = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    safe = model.replace(":", "-").replace("/", "-")
    print(f"=== bench model={model} iters={iters} ===")
    rows = []
    for key, desc in PARTS.items():
        name = f"{safe}__{key}"
        res = T.run(desc, name=name, model=model, iters=iters)  # compile-only mode
        compiled = res.get("png") is not None and res.get("error") is None
        rows.append((key, compiled, res.get("attempts"), res.get("png")))
        print(f"  {key:10} compiled={compiled} attempts={res.get('attempts')}")
    print("\n=== PNGs to inspect ===")
    for key, compiled, _, png in rows:
        if png:
            print(f"  {key:10} {png}")


if __name__ == "__main__":
    main()
