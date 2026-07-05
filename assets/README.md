# Brand assets

The SVGs are the source of truth. The raster files are exports of the
same design, kept in the repo because the Windows build and the README
need them directly.

| File        | Role                                                    |
|-------------|---------------------------------------------------------|
| `icon.svg`  | square app mark, master for the icons                   |
| `logo.svg`  | horizontal lockup (mark + wordmark), master for the README |
| `icon.png`  | 256px badge, used as the app window icon                |
| `icon.ico`  | multi-size icon embedded in the Windows build           |
| `logo.png`  | lockup shown at the top of the README                   |

## Re-exporting after editing an SVG

Any SVG renderer works. With [Inkscape](https://inkscape.org):

```bash
# square icon
inkscape icon.svg -o icon.png -w 256 -h 256
inkscape icon.svg -o icon-16.png  -w 16  -h 16
inkscape icon.svg -o icon-32.png  -w 32  -h 32
inkscape icon.svg -o icon-48.png  -w 48  -h 48
inkscape icon.svg -o icon-256.png -w 256 -h 256
# bundle the sizes into an .ico (ImageMagick)
magick icon-16.png icon-32.png icon-48.png icon-256.png icon.ico

# README lockup
inkscape logo.svg -o logo.png -w 760
```
