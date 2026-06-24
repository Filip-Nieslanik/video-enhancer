"""Unit tests for the pure parts of the engine.

These cover parsing and filter-graph assembly, which is where the fiddly
bugs hide. The actual ffmpeg/ncnn runs are exercised separately by hand
since they need the binaries and a real clip.
"""
import pytest

from core import (
    EnhanceConfig,
    VideoInfo,
    build_filter_chain,
    parse_ffmpeg_info,
    resolve_model,
)


# -- VideoInfo formatting ---------------------------------------------------
def test_resolution_formats_when_known():
    assert VideoInfo("x", width=1920, height=1080).resolution == "1920x1080"


def test_resolution_unknown_is_placeholder():
    assert VideoInfo("x").resolution == "?"


@pytest.mark.parametrize("seconds,expected", [
    (0, "0:00"),
    (5, "0:05"),
    (65, "1:05"),
    (3661, "1:01:01"),
])
def test_duration_str(seconds, expected):
    assert VideoInfo("x", duration=seconds).duration_str == expected


# -- ffmpeg banner parsing --------------------------------------------------
SAMPLE_BANNER = """
Input #0, mov,mp4, from 'clip.mov':
  Duration: 00:06:04.41, start: 0.000000, bitrate: 9826 kb/s
  Stream #0:0: Video: hevc (Main), yuv420p, 1920x1080, 9690 kb/s, 24 fps, 24 tbr
  Stream #0:1: Audio: aac (LC), 48000 Hz, stereo, fltp, 128 kb/s
"""


def test_parse_duration():
    info = parse_ffmpeg_info(SAMPLE_BANNER, VideoInfo("clip.mov"))
    assert info.duration == pytest.approx(364.41, abs=0.01)


def test_parse_resolution_and_fps():
    info = parse_ffmpeg_info(SAMPLE_BANNER, VideoInfo("clip.mov"))
    assert (info.width, info.height) == (1920, 1080)
    assert info.fps == pytest.approx(24.0)


def test_parse_codec_and_audio():
    info = parse_ffmpeg_info(SAMPLE_BANNER, VideoInfo("clip.mov"))
    assert info.codec == "hevc"
    assert info.has_audio is True


def test_parse_no_audio_stream():
    banner = "Stream #0:0: Video: h264, yuv420p, 640x480, 30 fps"
    info = parse_ffmpeg_info(banner, VideoInfo("x"))
    assert info.has_audio is False


# -- model resolution -------------------------------------------------------
@pytest.mark.parametrize("scale", [2, 3, 4])
def test_auto_model_picks_animevideov3_for_scale(scale):
    model, out_scale = resolve_model("auto", scale)
    assert model == f"realesr-animevideov3-x{scale}"
    assert out_scale == scale


def test_x4plus_forces_scale_four():
    model, scale = resolve_model("realesrgan-x4plus", 2)
    assert model == "realesrgan-x4plus"
    assert scale == 4


# -- filter chain -----------------------------------------------------------
def test_chain_is_none_when_everything_neutral():
    cfg = EnhanceConfig(denoise=0, sharpen=0, contrast=1.0,
                        brightness=0.0, saturation=1.0)
    assert build_filter_chain(cfg) is None


def test_chain_includes_denoise():
    cfg = EnhanceConfig(denoise=3, sharpen=0, contrast=1.0,
                        brightness=0.0, saturation=1.0)
    assert build_filter_chain(cfg) == "hqdn3d=3:3:3:3"


def test_chain_includes_eq_only_when_colour_changed():
    cfg = EnhanceConfig(denoise=0, sharpen=0, contrast=1.1,
                        brightness=0.0, saturation=1.0)
    assert build_filter_chain(cfg) == "eq=contrast=1.1:brightness=0.0:saturation=1.0"


def test_chain_orders_denoise_before_sharpen():
    cfg = EnhanceConfig(denoise=2, sharpen=1.0, contrast=1.0,
                        brightness=0.0, saturation=1.0)
    chain = build_filter_chain(cfg)
    assert chain.index("hqdn3d") < chain.index("unsharp")


def test_chain_inserts_stabilize_transform():
    cfg = EnhanceConfig(denoise=0, sharpen=0, contrast=1.0,
                        brightness=0.0, saturation=1.0)
    chain = build_filter_chain(cfg, stabilize_trf="t.trf")
    assert "vidstabtransform" in chain
    assert "input=t.trf" in chain
