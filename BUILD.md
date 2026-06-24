# Building installers

This document covers turning the source into a distributable app on
Windows and macOS, and the honest story on getting past OS security
warnings.

## Windows

1. Build the app bundle:

   ```powershell
   pip install -r requirements.txt pyinstaller
   python scripts\download_models.py
   pyinstaller packaging\windows.spec
   ```

   This writes `dist\VideoEnhancer\` (a one-dir bundle with the exe,
   ffmpeg and the AI models).

2. Build the installer with [Inno Setup 6](https://jrsoftware.org/isdl.php):

   ```powershell
   iscc packaging\installer.iss
   ```

   Output: `installer-output\VideoEnhancer-Setup.exe`.

### Why one-dir and no UPX

A single `--onefile` exe unpacks itself to a temp directory on every
launch. That pattern, plus UPX compression, is exactly what cheap malware
does, so SmartScreen and several AV engines flag it. The spec uses a
one-dir layout with UPX disabled and a proper version resource, which
keeps false positives down.

### Avoiding the SmartScreen warning (the real answer)

An unsigned executable will show "Windows protected your PC" until enough
people run it to build reputation. There is no flag that removes this;
the only reliable fix is an **Authenticode code-signing certificate**:

```powershell
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 ^
  /a "installer-output\VideoEnhancer-Setup.exe"
```

- A standard OV certificate (~$100-200/yr) signs the binary; reputation
  still builds over time.
- An EV certificate clears SmartScreen immediately but costs more and
  needs a hardware token.

Without a certificate, users can click **More info -> Run anyway**.

## macOS

```bash
bash packaging/build_macos.sh
```

Produces `installer-output/VideoEnhancer.dmg`.

### Gatekeeper

An unsigned `.app` is blocked with "cannot be opened because the
developer cannot be verified". Options:

- **First launch workaround:** right-click the app -> *Open* -> *Open*.
- **Proper fix:** an Apple Developer ID ($99/yr), then sign and notarize:

  ```bash
  codesign --deep --force --options runtime \
    --sign "Developer ID Application: Your Name (TEAMID)" \
    "dist/Video Enhancer.app"

  xcrun notarytool submit installer-output/VideoEnhancer.dmg \
    --apple-id you@example.com --team-id TEAMID --wait

  xcrun stapler staple installer-output/VideoEnhancer.dmg
  ```

## Summary

| Platform | Output                         | Quarantine-free requires |
|----------|--------------------------------|--------------------------|
| Windows  | `VideoEnhancer-Setup.exe`      | Authenticode certificate |
| macOS    | `VideoEnhancer.dmg`            | Developer ID + notarize  |

The packaging scripts produce working, professional installers. Clearing
the OS reputation prompts is a signing/account matter, not something the
build itself can bypass.
