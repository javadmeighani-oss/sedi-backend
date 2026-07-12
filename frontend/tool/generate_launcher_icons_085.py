"""Generate 85%-scaled Sedi Android launcher icons from canonical assets.

Legacy and adaptive pipelines differ because the previously generated HEAD
adaptive foreground mipmaps were already inset relative to a linear downscale of
the canonical 1024 foreground. Adaptive targets are therefore derived from the
measured HEAD per-density visible bounds, not only from the canonical master crop.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

SCALE = 0.85
CANONICAL_CANVAS = 1024
ALPHA_THRESHOLD = 8
TOLERANCE_PX = 1
TOLERANCE_RATIO = 0.02

DENSITIES = {
    'mdpi': {'launcher': 48, 'foreground': 108},
    'hdpi': {'launcher': 72, 'foreground': 162},
    'xhdpi': {'launcher': 96, 'foreground': 216},
    'xxhdpi': {'launcher': 144, 'foreground': 324},
    'xxxhdpi': {'launcher': 192, 'foreground': 432},
}

# Measured alpha-visible diameter from HEAD 5033433 adaptive foregrounds.
HEAD_ADAPTIVE_VISIBLE = {
    'mdpi': 68,
    'hdpi': 102,
    'xhdpi': 134,
    'xxhdpi': 202,
    'xxxhdpi': 268,
}

# Measured olive-visible diameter from HEAD 5033433 legacy launcher icons.
HEAD_LEGACY_VISIBLE = {
    'mdpi': 34,
    'hdpi': 50,
    'xhdpi': 66,
    'xxhdpi': 98,
    'xxxhdpi': 132,
}

CANONICAL_FOREGROUND = 'assets/images/sedi_app_icon_foreground.png'
CANONICAL_FULL = 'assets/images/sedi_app_icon.png'


def alpha_bbox(img: Image.Image) -> tuple[int, int, int, int]:
    px = img.load()
    w, h = img.size
    xs: list[int] = []
    ys: list[int] = []
    for y in range(h):
        for x in range(w):
            if px[x, y][3] > ALPHA_THRESHOLD:
                xs.append(x)
                ys.append(y)
    if not xs:
        raise RuntimeError('empty alpha bbox')
    return (min(xs), min(ys), max(xs), max(ys))


def olive_bbox(img: Image.Image) -> tuple[int, int, int, int]:
    px = img.load()
    w, h = img.size
    xs: list[int] = []
    ys: list[int] = []
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a > ALPHA_THRESHOLD and not (r > 250 and g > 250 and b > 250):
                xs.append(x)
                ys.append(y)
    if not xs:
        raise RuntimeError('empty olive bbox')
    return (min(xs), min(ys), max(xs), max(ys))


def bbox_side(bbox: tuple[int, int, int, int]) -> int:
    return bbox[2] - bbox[0] + 1


def bbox_center(bbox: tuple[int, int, int, int]) -> tuple[float, float]:
    return (
        (bbox[0] + bbox[2]) / 2.0,
        (bbox[1] + bbox[3]) / 2.0,
    )


def load_canonical_crop(src: Path) -> tuple[Image.Image, tuple[int, int, int, int]]:
    img = Image.open(src).convert('RGBA')
    bbox = alpha_bbox(img)
    return img.crop(bbox), bbox


def compose_centered(
    composition: Image.Image,
    canvas_size: int,
    target_side: int,
) -> Image.Image:
    scaled = composition.resize(
        (target_side, target_side),
        Image.Resampling.LANCZOS,
    )
    canvas = Image.new('RGBA', (canvas_size, canvas_size), (0, 0, 0, 0))
    offset = (canvas_size - target_side) // 2
    canvas.paste(scaled, (offset, offset), scaled)
    return canvas


def compose_legacy_centered(
    composition: Image.Image,
    canvas_size: int,
    target_side: int,
) -> Image.Image:
    scaled = composition.resize(
        (target_side, target_side),
        Image.Resampling.LANCZOS,
    )
    canvas = Image.new('RGBA', (canvas_size, canvas_size), (255, 255, 255, 255))
    offset = (canvas_size - target_side) // 2
    canvas.paste(scaled, (offset, offset), scaled)
    return canvas


def adaptive_target_visible(density: str) -> int:
    return max(1, round(HEAD_ADAPTIVE_VISIBLE[density] * SCALE))


def legacy_target_visible(density: str) -> int:
    return max(1, round(HEAD_LEGACY_VISIBLE[density] * SCALE))


def generate_adaptive_foregrounds(base: Path, crop: Image.Image) -> dict[str, int]:
    written: dict[str, int] = {}
    for density, sizes in DENSITIES.items():
        target = adaptive_target_visible(density)
        canvas = sizes['foreground']
        out = compose_centered(crop, canvas, target)
        out_path = base / f'android/app/src/main/res/mipmap-{density}/ic_launcher_foreground.png'
        out.save(out_path)
        written[density] = target
    return written


def generate_legacy_icons(base: Path, crop: Image.Image) -> dict[str, int]:
    """Legacy pipeline: scale canonical olive composition to 85% of HEAD legacy."""
    written: dict[str, int] = {}
    for density, sizes in DENSITIES.items():
        target = legacy_target_visible(density)
        canvas = sizes['launcher']
        out = compose_legacy_centered(crop, canvas, target)
        out_dir = base / f'android/app/src/main/res/mipmap-{density}'
        out.save(out_dir / 'ic_launcher.png')
        out.save(out_dir / 'ic_launcher_round.png')
        written[density] = target
    return written


def ratio_within_tolerance(actual: int, expected: int, baseline: int) -> bool:
    if abs(actual - expected) <= TOLERANCE_PX:
        return True
    if baseline <= 0:
        return False
    return abs((actual / baseline) - SCALE) <= TOLERANCE_RATIO


def verify_outputs(base: Path, adaptive_only: bool = False) -> None:
    errors: list[str] = []

    for density, sizes in DENSITIES.items():
        fg_path = base / f'android/app/src/main/res/mipmap-{density}/ic_launcher_foreground.png'
        fg_img = Image.open(fg_path).convert('RGBA')
        if fg_img.size != (sizes['foreground'], sizes['foreground']):
            errors.append(
                f'{density} foreground size {fg_img.size} != '
                f'{sizes["foreground"]}x{sizes["foreground"]}',
            )

        fg_bbox = alpha_bbox(fg_img)
        fg_side = bbox_side(fg_bbox)
        head_fg = HEAD_ADAPTIVE_VISIBLE[density]
        target_fg = adaptive_target_visible(density)
        if not ratio_within_tolerance(fg_side, target_fg, head_fg):
            errors.append(
                f'{density} adaptive visible {fg_side} expected ~{target_fg} '
                f'(HEAD {head_fg}, ratio {fg_side/head_fg:.3f})',
            )

        center = bbox_center(fg_bbox)
        expected_center = sizes['foreground'] / 2.0
        if abs(center[0] - expected_center) > 1.0 or abs(center[1] - expected_center) > 1.0:
            errors.append(
                f'{density} adaptive off-center {center} expected ~({expected_center}, {expected_center})',
            )

        if adaptive_only:
            continue

        for name in ('ic_launcher.png', 'ic_launcher_round.png'):
            path = base / f'android/app/src/main/res/mipmap-{density}/{name}'
            img = Image.open(path).convert('RGBA')
            if img.size != (sizes['launcher'], sizes['launcher']):
                errors.append(f'{density} {name} size {img.size} incorrect')
            olive_side = bbox_side(olive_bbox(img))
            head_legacy = HEAD_LEGACY_VISIBLE[density]
            target_legacy = legacy_target_visible(density)
            if not ratio_within_tolerance(olive_side, target_legacy, head_legacy):
                errors.append(
                    f'{density} {name} olive {olive_side} expected ~{target_legacy} '
                    f'(HEAD {head_legacy}, ratio {olive_side/head_legacy:.3f})',
                )

    bundled_derived = [
        base / 'assets/images/sedi_app_icon_scaled_085.png',
        base / 'assets/images/sedi_app_icon_foreground_scaled_085.png',
    ]
    for path in bundled_derived:
        if path.exists():
            errors.append(f'bundled intermediate must be removed: {path}')

    if errors:
        raise SystemExit('Verification failed:\n- ' + '\n- '.join(errors))


def effective_adaptive_master_visible() -> int:
    """Documented equivalent 1024px master visible diameter for adaptive pipeline."""
    xxxhdpi_target = adaptive_target_visible('xxxhdpi')
    return round(xxxhdpi_target * CANONICAL_CANVAS / DENSITIES['xxxhdpi']['foreground'])


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    include_legacy = '--legacy' in args
    adaptive_only = '--adaptive-only' in args or not include_legacy

    base = Path(__file__).resolve().parents[1]
    foreground_src = base / CANONICAL_FOREGROUND
    full_src = base / CANONICAL_FULL

    if not foreground_src.exists() or not full_src.exists():
        raise SystemExit('Canonical launcher source assets are missing')

    fg_crop, fg_bbox = load_canonical_crop(foreground_src)
    canonical_side = bbox_side(fg_bbox)

    if include_legacy:
        full_img = Image.open(full_src).convert('RGBA')
        legacy_crop = full_img.crop(olive_bbox(full_img))
        generate_legacy_icons(base, legacy_crop)

    targets = generate_adaptive_foregrounds(base, fg_crop)
    verify_outputs(base, adaptive_only=adaptive_only)

    print('canonical foreground crop', fg_bbox, 'side', canonical_side)
    print('adaptive effective master visible @1024', effective_adaptive_master_visible())
    print('adaptive targets', targets)
    if include_legacy:
        print('legacy targets', {d: legacy_target_visible(d) for d in DENSITIES})
    print('verification passed')


if __name__ == '__main__':
    main()
