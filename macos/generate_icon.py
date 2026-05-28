"""
Generate ScreenMind.icns from the brain.head.profile SF Symbol.

Renders the SF Symbol at iconutil's expected sizes, drops them in an iconset
directory, and assembles the .icns. Produces macos/ScreenMind.icns.
"""
import subprocess
import sys
from pathlib import Path

from AppKit import (  # type: ignore
    NSBitmapImageFileTypePNG,
    NSBitmapImageRep,
    NSColor,
    NSCompositingOperationCopy,
    NSCompositingOperationSourceOver,
    NSGraphicsContext,
    NSImage,
    NSImageSymbolConfiguration,
)
from Foundation import NSMakeRect  # type: ignore

# (filename, pixel size)
ICONSET_FILES = [
    ("icon_16x16.png", 16),
    ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),
    ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),
    ("icon_512x512@2x.png", 1024),
]

SYMBOL = "brain.head.profile"
# Purple-violet, gradient-friendly. Matches ScreenMind's marketing 8B5CF6.
BG_COLOR = NSColor.colorWithSRGBRed_green_blue_alpha_(0.545, 0.361, 0.965, 1.0)
GLYPH_COLOR = NSColor.whiteColor()


def _make_bitmap(size: int) -> NSBitmapImageRep:
    rep = (
        NSBitmapImageRep.alloc()
        .initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
            None, size, size, 8, 4, True, False, "NSDeviceRGBColorSpace", 0, 32
        )
    )
    return rep


def _draw_rounded_bg(size: int) -> None:
    # Use a 22% corner-radius — close to macOS's superellipse but simpler.
    from AppKit import NSBezierPath  # type: ignore

    radius = size * 0.22
    rect = NSMakeRect(0, 0, size, size)
    path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(rect, radius, radius)
    BG_COLOR.setFill()
    path.fill()


def _draw_symbol(size: int) -> None:
    base = NSImage.imageWithSystemSymbolName_accessibilityDescription_(SYMBOL, None)
    if base is None:
        raise RuntimeError(f"SF Symbol {SYMBOL!r} not available")
    config = NSImageSymbolConfiguration.configurationWithPointSize_weight_(
        size * 0.62, 5  # 5 = bold
    )
    sized = base.imageWithSymbolConfiguration_(config)

    # Compute the centered draw rect. The symbol image's intrinsic size after
    # configuration is roughly proportional to point size; just center on canvas.
    img_size = sized.size()
    x = (size - img_size.width) / 2
    y = (size - img_size.height) / 2

    GLYPH_COLOR.set()
    sized.drawInRect_fromRect_operation_fraction_respectFlipped_hints_(
        NSMakeRect(x, y, img_size.width, img_size.height),
        NSMakeRect(0, 0, 0, 0),
        NSCompositingOperationSourceOver,
        1.0,
        True,
        None,
    )


def render_size(size: int, path: Path) -> None:
    rep = _make_bitmap(size)
    ctx = NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(ctx)
    _draw_rounded_bg(size)
    _draw_symbol(size)
    NSGraphicsContext.restoreGraphicsState()
    png = rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, {})
    png.writeToFile_atomically_(str(path), True)


def main() -> int:
    out_dir = Path(__file__).resolve().parent
    iconset = out_dir / "ScreenMind.iconset"
    iconset.mkdir(exist_ok=True)

    for fname, size in ICONSET_FILES:
        target = iconset / fname
        render_size(size, target)
        print(f"wrote {target.relative_to(out_dir.parent)} ({size}x{size})")

    icns = out_dir / "ScreenMind.icns"
    subprocess.check_call(["iconutil", "-c", "icns", "-o", str(icns), str(iconset)])
    print(f"\n→ {icns.relative_to(out_dir.parent)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
