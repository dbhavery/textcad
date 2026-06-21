"""Command-line entry point: `textcad "a hex nut..." --inspect`."""
from __future__ import annotations

import argparse

from .loop import run


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        prog="textcad",
        description="Natural language -> OpenSCAD parametric CAD via a local agentic loop.")
    ap.add_argument("description", help="plain-English part description")
    ap.add_argument("--name", default="part", help="output basename (out/<name>.scad|png|stl)")
    ap.add_argument("--model", default="qwen2.5-coder:32b", help="Ollama model for codegen")
    ap.add_argument("--iters", type=int, default=3, help="max generate/fix attempts")
    ap.add_argument("--inspect", nargs="?", const="qwen2.5vl:7b", default=None,
                    metavar="VLM_MODEL",
                    help="enable the local vision-model inspector (default qwen2.5vl:7b)")
    ap.add_argument("--out", default="out", help="output directory (default: ./out)")
    args = ap.parse_args(argv)

    inspector = None
    if args.inspect:
        from .inspector import make_vlm_inspector
        inspector = make_vlm_inspector(args.inspect)

    result = run(args.description, name=args.name, model=args.model,
                 iters=args.iters, inspector=inspector, out_dir=args.out)

    print("\n=== RESULT ===")
    for k in ("description", "attempts", "scad", "png", "stl", "error"):
        if result.get(k) not in (None, ""):
            print(f"{k:12}: {result[k]}")


if __name__ == "__main__":
    main()
