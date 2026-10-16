"""Генерация иконок PWA PetSpace.

Запуск (нужен Pillow):
    python scripts/generate-icons.py

Иконки кладутся в public/icons. Фон фирменный (#BDB1E3), лапа белая.
Для maskable-иконки контент уменьшен, чтобы попадать в safe zone Android.
"""

from pathlib import Path

from PIL import Image, ImageDraw

BRAND = (189, 177, 227, 255)  # #BDB1E3
WHITE = (255, 255, 255, 255)
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "public" / "icons"
SCALE = 4  # рисуем крупнее и уменьшаем — так края получаются гладкими

TOES = ((0.23, 0.43, 0.092), (0.41, 0.29, 0.086), (0.59, 0.29, 0.086), (0.77, 0.43, 0.092))
PAD = (0.5, 0.68, 0.235, 0.155)


def draw_icon(size: int, content_ratio: float) -> Image.Image:
    side = size * SCALE
    image = Image.new("RGBA", (side, side), BRAND)
    draw = ImageDraw.Draw(image)

    content = side * content_ratio
    offset = (side - content) / 2

    def center(x: float, y: float) -> tuple[float, float]:
        return offset + content * x, offset + content * y

    for cx, cy, radius in TOES:
        x, y = center(cx, cy)
        r = content * radius
        draw.ellipse([x - r, y - r, x + r, y + r], fill=WHITE)

    cx, cy, rx, ry = PAD
    x, y = center(cx, cy)
    draw.ellipse([x - content * rx, y - content * ry, x + content * rx, y + content * ry], fill=WHITE)

    return image.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    icons = {
        "icon-192.png": draw_icon(192, 0.78),
        "icon-512.png": draw_icon(512, 0.78),
        "icon-maskable-512.png": draw_icon(512, 0.60),
        "apple-touch-icon.png": draw_icon(180, 0.78),
    }
    for name, image in icons.items():
        path = OUTPUT_DIR / name
        image.save(path)
        print(f"{path.relative_to(OUTPUT_DIR.parents[1])}: {image.size[0]}x{image.size[1]}")


if __name__ == "__main__":
    main()
