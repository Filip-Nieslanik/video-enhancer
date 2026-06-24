"""Command-line front-end. Same engine as the GUI, handy for batch jobs.

    python cli.py clip.mov                 # best defaults, 2x AI + denoise
    python cli.py clip.mov --scale 4       # 4x
    python cli.py clip.mov --no-ai         # ffmpeg-only denoise/colour
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core import VideoProcessor, EnhanceConfig


def _bar(pct: float, width: int = 28) -> str:
    filled = int(width * pct / 100)
    return "#" * filled + "-" * (width - filled)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Enhance video quality with AI upscaling and ffmpeg.")
    ap.add_argument("input", help="input video file")
    ap.add_argument("-o", "--output", help="output file (default: <name>_enhanced.mp4)")
    ap.add_argument("--scale", type=int, default=2, choices=[1, 2, 3, 4],
                    help="AI upscale factor; 1 disables upscaling (default: 2)")
    ap.add_argument("--no-ai", action="store_true", help="skip AI upscaling entirely")
    ap.add_argument("--denoise", type=float, default=4.0, help="denoise strength 0-10 (default: 4)")
    ap.add_argument("--sharpen", type=float, default=0.0, help="sharpen 0-3 (default: 0)")
    ap.add_argument("--contrast", type=float, default=1.0)
    ap.add_argument("--brightness", type=float, default=0.0)
    ap.add_argument("--saturation", type=float, default=1.0)
    ap.add_argument("--stabilize", action="store_true", help="stabilize shaky footage (no-AI mode)")
    ap.add_argument("--crf", type=int, default=16, help="quality 0-51, lower is better (default: 16)")
    ap.add_argument("--preset", default="slow",
                    choices=["ultrafast", "superfast", "veryfast", "faster", "fast",
                             "medium", "slow", "slower", "veryslow"])
    args = ap.parse_args(argv)

    src = Path(args.input)
    if not src.exists():
        print(f"error: file not found: {src}", file=sys.stderr)
        return 1

    out = Path(args.output) if args.output else src.with_name(src.stem + "_enhanced.mp4")

    cfg = EnhanceConfig(
        use_ai=not args.no_ai and args.scale > 1,
        scale=args.scale,
        denoise=args.denoise,
        sharpen=args.sharpen,
        contrast=args.contrast,
        brightness=args.brightness,
        saturation=args.saturation,
        stabilize=args.stabilize,
        crf=args.crf,
        preset=args.preset,
    )

    if cfg.use_ai and not VideoProcessor.ai_available():
        print("warning: Real-ESRGAN not found, falling back to ffmpeg only.\n"
              "         run scripts/download_models.py to enable AI upscaling.",
              file=sys.stderr)
        cfg.use_ai = False

    state = {"stage": ""}

    def progress(pct, stage, detail=""):
        end = "\n" if stage != state["stage"] and state["stage"] else ""
        if stage != state["stage"]:
            state["stage"] = stage
        print(f"\r  {stage:<18} [{_bar(pct)}] {pct:5.1f}%  {detail}", end="", flush=True)

    proc = VideoProcessor(on_progress=progress)
    info = proc.probe(str(src))
    print(f"input : {src.name}  {info.resolution}  {info.duration_str}  {info.fps:.0f}fps")
    print(f"output: {out.name}")

    try:
        proc.process(str(src), str(out), cfg, info)
    except KeyboardInterrupt:
        proc.cancel()
        print("\naborted.")
        return 130
    except Exception as e:
        print(f"\nerror: {e}", file=sys.stderr)
        return 1

    mb = out.stat().st_size / 1024 / 1024
    print(f"\ndone: {out}  ({mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
