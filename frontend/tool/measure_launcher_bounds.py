"""Read-only measurement of launcher icon visible bounds from HEAD and working tree."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

DENSITIES = ['mdpi', 'hdpi', 'xhdpi', 'xxhdpi', 'xxxhdpi']
FILES = ['ic_launcher.png', 'ic_launcher_foreground.png', 'ic_launcher_round.png']


def alpha_bbox(img: Image.Image) -> tuple[int, int, int, int]:
    px = img.load()
    w, h = img.size
    xs: list[int] = []
    ys: list[int] = []
    for y in range(h):
        for x in range(w):
            if px[x, y][3] > 8:
                xs.append(x)
                ys.append(y)
    if not xs:
        return (0, 0, 0, 0)
    return (min(xs), min(ys), max(xs), max(ys))


def olive_bbox(img: Image.Image) -> tuple[int, int, int, int]:
    px = img.load()
    w, h = img.size
    xs: list[int] = []
    ys: list[int] = []
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a > 8 and not (r > 250 and g > 250 and b > 250):
                xs.append(x)
                ys.append(y)
    if not xs:
        return (0, 0, 0, 0)
    return (min(xs), min(ys), max(xs), max(ys))


def side(bbox: tuple[int, int, int, int]) -> int:
    return bbox[2] - bbox[0] + 1 if bbox != (0, 0, 0, 0) else 0


def load_git(repo: Path, git_path: str) -> Image.Image:
    data = subprocess.check_output(['git', 'show', f'HEAD:{git_path}'], cwd=repo)
    tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    tmp.write(data)
    tmp.close()
    return Image.open(tmp.name).convert('RGBA')


def main() -> None:
    base = Path(__file__).resolve().parents[1]
    repo = base.parent
    print('density,file,source,size,fg_alpha,legacy_olive,round_olive')
    for density in DENSITIES:
        for name in FILES:
            rel = f'frontend/android/app/src/main/res/mipmap-{density}/{name}'
            head = load_git(repo, rel)
            work = Image.open(base / rel.replace('frontend/', '')).convert('RGBA')
            for label, img in [('HEAD', head), ('WORK', work)]:
                fg = side(alpha_bbox(img)) if 'foreground' in name else 0
                olive = side(olive_bbox(img)) if 'foreground' not in name else 0
                print(
                    f'{density},{name},{label},{img.size[0]}x{img.size[1]},'
                    f'{fg},{olive},{olive}'
                )


if __name__ == '__main__':
    main()
