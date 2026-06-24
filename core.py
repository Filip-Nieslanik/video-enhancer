"""Processing engine for Video Enhancer.

Wraps ffmpeg and the Real-ESRGAN ncnn-vulkan binary into a single
pipeline: probe, optional AI upscale, denoise/colour, encode. The GUI
and the CLI both drive this module; nothing here touches Tk.

Long operations report progress through a callback and honour a
cooperative cancel flag so the UI stays responsive.
"""
from __future__ import annotations

import os
import re
import sys
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import imageio_ffmpeg


def _base_dir() -> Path:
    """Root used to locate bundled resources.

    PyInstaller unpacks data into sys._MEIPASS at runtime; in a normal
    checkout it is just the folder this file lives in.
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


BASE_DIR = _base_dir()
ESRGAN_DIR = BASE_DIR / "realesrgan-ncnn"
ESRGAN_EXE = ESRGAN_DIR / "realesrgan-ncnn-vulkan.exe"
ESRGAN_MODELS = ESRGAN_DIR / "models"

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

# Keep spawned console processes from flashing a window on Windows.
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _popen(cmd, **kwargs):
    return subprocess.Popen(
        cmd,
        stdout=kwargs.pop("stdout", subprocess.PIPE),
        stderr=kwargs.pop("stderr", subprocess.STDOUT),
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=_NO_WINDOW,
        **kwargs,
    )


def _run(cmd, **kwargs):
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=_NO_WINDOW,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Value types
# ---------------------------------------------------------------------------
@dataclass
class VideoInfo:
    path: str
    width: int = 0
    height: int = 0
    fps: float = 24.0
    duration: float = 0.0
    size_mb: float = 0.0
    codec: str = ""
    has_audio: bool = False

    @property
    def resolution(self) -> str:
        return f"{self.width}x{self.height}" if self.width and self.height else "?"

    @property
    def duration_str(self) -> str:
        m, s = divmod(int(self.duration), 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


@dataclass
class EnhanceConfig:
    use_ai: bool = True
    scale: int = 2              # 1 means no upscale
    ai_model: str = "auto"      # auto | realesrgan-x4plus | realesr-animevideov3
    denoise: float = 4.0        # hqdn3d strength, 0 disables
    sharpen: float = 0.0        # unsharp amount; AI already adds detail
    contrast: float = 1.0
    brightness: float = 0.0
    saturation: float = 1.0
    stabilize: bool = False
    crf: int = 16               # libx264 quality, lower is better
    preset: str = "slow"
    tile: int = 0               # ncnn tile size, 0 lets it decide


class Cancelled(Exception):
    """Raised when the caller asked to stop mid-pipeline."""


# ---------------------------------------------------------------------------
# Pure helpers (kept free of side effects so they are easy to test)
# ---------------------------------------------------------------------------
_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):([\d.]+)")
_TIME_RE = re.compile(r"time=(\d+):(\d+):([\d.]+)")
_RES_RE = re.compile(r"(\d{2,5})x(\d{2,5})")
_FPS_RE = re.compile(r"([\d.]+)\s*fps")
_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)%")


def parse_ffmpeg_info(stderr: str, info: VideoInfo) -> VideoInfo:
    """Fill a VideoInfo from the banner ffmpeg prints on stderr."""
    for line in stderr.splitlines():
        if "Duration:" in line:
            m = _DURATION_RE.search(line)
            if m:
                h, mn, s = m.groups()
                info.duration = int(h) * 3600 + int(mn) * 60 + float(s)
        elif "Video:" in line and "Stream" in line:
            res = _RES_RE.search(line)
            if res:
                info.width, info.height = int(res.group(1)), int(res.group(2))
            fps = _FPS_RE.search(line)
            if fps:
                try:
                    info.fps = float(fps.group(1))
                except ValueError:
                    pass
            codec = re.search(r"Video:\s*(\w+)", line)
            if codec:
                info.codec = codec.group(1)
        elif "Audio:" in line and "Stream" in line:
            info.has_audio = True
    return info


def resolve_model(model: str, scale: int) -> tuple[str, int]:
    """Map a config model name to the actual ncnn model and scale."""
    if model == "auto":
        return f"realesr-animevideov3-x{scale}", scale
    if model == "realesrgan-x4plus":
        return model, 4  # this model only ships an x4 variant
    return model, scale


def build_filter_chain(config: EnhanceConfig, stabilize_trf: str | None = None) -> str | None:
    """Assemble the -vf graph for the encode step. Returns None if empty."""
    parts = []
    if config.denoise > 0:
        parts.append(f"hqdn3d={config.denoise}:{config.denoise}:3:3")
    if stabilize_trf:
        parts.append(f"vidstabtransform=smoothing=10:input={stabilize_trf}")
    if config.sharpen > 0:
        parts.append(f"unsharp=5:5:{config.sharpen}:5:5:0")
    if config.contrast != 1.0 or config.brightness != 0.0 or config.saturation != 1.0:
        parts.append(
            f"eq=contrast={config.contrast}:brightness={config.brightness}"
            f":saturation={config.saturation}"
        )
    return ",".join(parts) if parts else None


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
class VideoProcessor:
    def __init__(self, on_progress=None, on_log=None):
        self.on_progress = on_progress or (lambda pct, stage, detail="": None)
        self.on_log = on_log or (lambda msg: None)
        self._proc: subprocess.Popen | None = None
        self._cancelled = False

    @staticmethod
    def ai_available() -> bool:
        return ESRGAN_EXE.exists()

    def cancel(self):
        self._cancelled = True
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass

    def probe(self, path: str) -> VideoInfo:
        info = VideoInfo(path=path)
        p = Path(path)
        if p.exists():
            info.size_mb = p.stat().st_size / 1024 / 1024
        return parse_ffmpeg_info(_run([FFMPEG, "-i", path, "-hide_banner"]).stderr or "", info)

    def process(self, input_path: str, output_path: str,
                config: EnhanceConfig, info: VideoInfo | None = None):
        self._cancelled = False
        info = info or self.probe(input_path)
        if config.use_ai and config.scale > 1 and self.ai_available():
            self._process_ai(input_path, output_path, config, info)
        else:
            self._process_plain(input_path, output_path, config, info)

    # -- internals ----------------------------------------------------------
    def _abort_if_cancelled(self):
        if self._cancelled:
            raise Cancelled()

    def _process_plain(self, input_path, output_path, config, info):
        trf = None
        if config.stabilize:
            # vidstab needs a detection pass before it can transform.
            self.on_progress(2, "Analyzing motion", "stabilization 1/2")
            trf = str(Path(tempfile.gettempdir()) / "ve_transforms.trf")
            self._ffmpeg(
                [FFMPEG, "-y", "-i", input_path, "-vf",
                 f"vidstabdetect=shakiness=5:accuracy=15:result={trf}",
                 "-f", "null", "-"],
                info.duration, base=2, span=18, stage="Analyzing motion")
            self._abort_if_cancelled()

        vf = build_filter_chain(config, trf)
        cmd = [FFMPEG, "-y", "-i", input_path]
        if vf:
            cmd += ["-vf", vf]
        cmd += ["-c:v", "libx264", "-crf", str(config.crf),
                "-preset", config.preset, "-c:a", "copy", output_path]

        base = 20 if config.stabilize else 0
        self.on_progress(base, "Encoding")
        self._ffmpeg(cmd, info.duration, base=base, span=100 - base, stage="Encoding")
        if trf and os.path.exists(trf):
            try:
                os.remove(trf)
            except OSError:
                pass
        self.on_progress(100, "Done")

    def _process_ai(self, input_path, output_path, config, info):
        model, scale = resolve_model(config.ai_model, config.scale)
        work = Path(tempfile.mkdtemp(prefix="ve_ai_"))
        src, dst = work / "in", work / "out"
        src.mkdir()
        dst.mkdir()
        try:
            # 1. split into frames (0-15%)
            self.on_progress(0, "Extracting frames", f"{info.fps:.0f} fps")
            self._ffmpeg(
                [FFMPEG, "-y", "-i", input_path, "-qscale:v", "1", "-qmin", "1",
                 str(src / "f%06d.png")],
                info.duration, base=0, span=15, stage="Extracting frames")
            self._abort_if_cancelled()
            total = len(list(src.glob("*.png")))
            self.on_log(f"extracted {total} frames")

            # 2. upscale every frame (15-80%)
            self.on_progress(15, "AI upscaling", f"{scale}x  {model}")
            self._esrgan(src, dst, scale, model, config.tile, base=15, span=65)
            self._abort_if_cancelled()

            # 3. stitch back together with the encode-time filters (80-100%)
            self.on_progress(80, "Encoding", "denoise + H.264")
            vf = build_filter_chain(config)  # stabilize not offered in AI mode
            cmd = [FFMPEG, "-y", "-framerate", str(info.fps),
                   "-i", str(dst / "f%06d.png")]
            if info.has_audio:
                cmd += ["-i", input_path, "-map", "0:v", "-map", "1:a?"]
            if vf:
                cmd += ["-vf", vf]
            cmd += ["-c:v", "libx264", "-crf", str(config.crf),
                    "-preset", config.preset, "-pix_fmt", "yuv420p"]
            if info.has_audio:
                cmd += ["-c:a", "aac", "-b:a", "192k"]
            cmd += [output_path]
            self._ffmpeg(cmd, info.duration, base=80, span=20, stage="Encoding")
            self.on_progress(100, "Done")
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def _esrgan(self, in_dir, out_dir, scale, model, tile, base, span):
        cmd = [str(ESRGAN_EXE), "-i", str(in_dir), "-o", str(out_dir),
               "-s", str(scale), "-n", model, "-m", str(ESRGAN_MODELS), "-f", "png"]
        if tile and tile > 0:
            cmd += ["-t", str(tile)]
        self.on_log("realesrgan: " + " ".join(cmd))
        self._proc = _popen(cmd, cwd=str(ESRGAN_DIR))

        # ncnn drives several GPU queues at once, so the percentages it
        # prints arrive out of order. Track the peak so progress only
        # ever moves forward.
        peak = 0.0
        for line in self._proc.stdout:
            if self._cancelled:
                break
            m = _PCT_RE.search(line)
            if m:
                peak = max(peak, float(m.group(1)))
                self.on_progress(base + span * peak / 100.0,
                                 "AI upscaling", f"{peak:.0f}%")
            elif line.strip():
                self.on_log(line.strip()[:120])
        self._proc.wait()
        rc = self._proc.returncode
        self._proc = None
        self._abort_if_cancelled()
        if not any(out_dir.glob("*.png")) and rc != 0:
            raise RuntimeError("Real-ESRGAN produced no frames")

    def _ffmpeg(self, cmd, duration, base, span, stage):
        self.on_log("ffmpeg: " + " ".join(str(c) for c in cmd))
        self._proc = _popen(cmd)
        for line in self._proc.stdout:
            if self._cancelled:
                break
            if "time=" in line and duration > 0:
                m = _TIME_RE.search(line)
                if m:
                    h, mn, s = m.groups()
                    cur = int(h) * 3600 + int(mn) * 60 + float(s)
                    pct = min(100.0, 100.0 * cur / duration)
                    self.on_progress(base + span * pct / 100.0, stage,
                                     f"{cur:.0f}s / {duration:.0f}s")
        self._proc.wait()
        rc = self._proc.returncode
        self._proc = None
        self._abort_if_cancelled()
        if rc != 0:
            raise RuntimeError(f"{stage} failed (ffmpeg exit {rc})")
