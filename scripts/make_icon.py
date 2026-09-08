"""Generate scripts/recall.ico — the taskbar and shortcut icon.

Committed as a .ico so nobody needs to run this; it lives here to record how the
icon was made and to regenerate it if the accent colour changes. Pillow comes
in with python-pptx, so there is no extra dependency.

    python scripts/make_icon.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 512                      # drawn large, downsampled into the .ico
ACCENT = (109, 59, 255, 255)    # --accent from the app's stylesheet
INK = (255, 255, 255, 255)

# A waveform: a recording, which is where everything in Recall starts. Bar
# heights as a fraction of the drawable height, deliberately uneven so it reads
# as speech rather than a chart.
BARS = [0.30, 0.58, 0.86, 0.44, 0.96, 0.62, 0.34]

ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]


def build() -> Image.Image:
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Rounded square, inset slightly so the corners are not clipped at 16px.
    pad = SIZE // 16
    draw.rounded_rectangle(
        [pad, pad, SIZE - pad, SIZE - pad], radius=SIZE // 5, fill=ACCENT
    )

    span = SIZE - 2 * pad
    bar_w = span * 0.075
    gap = (span * 0.62 - bar_w) / (len(BARS) - 1)
    start_x = SIZE / 2 - (span * 0.62) / 2
    mid_y = SIZE / 2
    max_h = span * 0.52

    for index, fraction in enumerate(BARS):
        x = start_x + index * gap
        half = max_h * fraction / 2
        draw.rounded_rectangle(
            [x, mid_y - half, x + bar_w, mid_y + half],
            radius=bar_w / 2,
            fill=INK,
        )

    return image


if __name__ == "__main__":
    target = Path(__file__).with_name("recall.ico")
    build().save(target, format="ICO", sizes=[(s, s) for s in ICO_SIZES])
    print(f"wrote {target} ({target.stat().st_size} bytes)")
