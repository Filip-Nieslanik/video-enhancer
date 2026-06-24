# PyInstaller spec for the Windows build.
#   pyinstaller packaging/windows.spec
#
# Produces dist/VideoEnhancer/ (one-dir). One-dir is deliberate: a single
# unsigned --onefile exe unpacks to temp at launch and trips SmartScreen and
# several AV engines far more often than a plain folder of files.

from PyInstaller.utils.hooks import collect_all, collect_data_files

datas = []
binaries = []
hiddenimports = []

# tkinterdnd2 ships a native tkdnd library that must travel with the app.
for collector in ("tkinterdnd2",):
    d, b, h = collect_all(collector)
    datas += d
    binaries += b
    hiddenimports += h

# the ffmpeg executable bundled by imageio-ffmpeg
datas += collect_data_files("imageio_ffmpeg")

# the AI binary + models, kept in the same relative folder the app expects
datas += [("../realesrgan-ncnn", "realesrgan-ncnn")]

# logo files used for the window icon at runtime
datas += [("../assets/icon.ico", "assets"), ("../assets/icon.png", "assets")]

block_cipher = None

a = Analysis(
    ["../VideoEnhancer.pyw"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["numpy", "cv2", "torch", "torchvision", "matplotlib"],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

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
    icon="../assets/icon.ico" if __import__("os").path.exists("../assets/icon.ico") else None,
    version="../packaging/version_info.txt"
        if __import__("os").path.exists("../packaging/version_info.txt") else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="VideoEnhancer",
)
