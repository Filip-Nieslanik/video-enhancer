"""Fetch the Real-ESRGAN ncnn-vulkan binary and models.

The binaries are ~45 MB and live outside the repo. Run this once after
cloning to enable AI upscaling:

    python scripts/download_models.py
"""
from __future__ import annotations

import sys
import urllib.request
import zipfile
from pathlib import Path

RELEASE = ("https://github.com/xinntao/Real-ESRGAN/releases/download/"
           "v0.2.5.0/realesrgan-ncnn-vulkan-20220424-windows.zip")
ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "realesrgan-ncnn"


def _report(block, block_size, total):
    if total <= 0:
        return
    done = min(100, block * block_size * 100 // total)
    sys.stdout.write(f"\r  downloading... {done}%")
    sys.stdout.flush()


def main() -> int:
    if (TARGET / "realesrgan-ncnn-vulkan.exe").exists():
        print("Real-ESRGAN already present, nothing to do.")
        return 0

    TARGET.mkdir(exist_ok=True)
    archive = TARGET / "_download.zip"
    print(f"Fetching {RELEASE}")
    urllib.request.urlretrieve(RELEASE, archive, _report)
    print("\n  extracting...")
    with zipfile.ZipFile(archive) as z:
        z.extractall(TARGET)
    archive.unlink()
    print(f"Done. Installed into {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
