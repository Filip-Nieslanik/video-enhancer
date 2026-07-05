# PyInstaller spec for the Windows build.
#   pyinstaller packaging/windows.spec
#
# Produces dist/VideoEnhancer/ (one-dir). One-dir is deliberate: a single
# unsigned --onefile exe unpacks to temp at launch and trips SmartScreen and
# several AV engines far more often than a plain folder of files.
import os
from PyInstaller.utils.hooks import collect_all

# SPECPATH is the folder holding this spec (…/packaging); the project root
# is its parent. Everything is resolved from here so the build works no
# matter what directory pyinstaller is invoked from.
ROOT = os.path.dirname(SPECPATH)
ESRGAN = os.path.join(ROOT, "realesrgan-ncnn")
ASSETS = os.path.join(ROOT, "assets")

datas, binaries, hiddenimports = [], [], []

# tkinterdnd2 ships a native tkdnd library; imageio-ffmpeg ships ffmpeg.
for pkg in ("tkinterdnd2", "imageio_ffmpeg"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# Real-ESRGAN: bundle only what the app runs with, not the sample images,
# readme or the debug runtime that ship in the upstream zip.
datas += [
    (os.path.join(ESRGAN, "realesrgan-ncnn-vulkan.exe"), "realesrgan-ncnn"),
    (os.path.join(ESRGAN, "vcomp140.dll"), "realesrgan-ncnn"),
    (os.path.join(ESRGAN, "models"), os.path.join("realesrgan-ncnn", "models")),
]

# window icon loaded at runtime
datas += [
    (os.path.join(ASSETS, "icon.ico"), "assets"),
    (os.path.join(ASSETS, "icon.png"), "assets"),
]

a = Analysis(
    [os.path.join(ROOT, "VideoEnhancer.pyw")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["torch", "torchvision", "matplotlib", "pandas", "scipy",
              "PyQt5", "PySide2", "notebook"],
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VideoEnhancer",
    debug=False,
    strip=False,
    upx=False,                 # UPX compression is a common AV false-positive trigger
    console=False,             # GUI app, no console window
    icon=os.path.join(ASSETS, "icon.ico"),
    version=os.path.join(SPECPATH, "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="VideoEnhancer",
)
