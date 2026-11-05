"""Generate synthetic, non-personal avatar images for demos and load tests."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "data" / "samples"


def _avatar(path: Path, *, skin: str, shirt: str, hair: str, eye: str) -> None:
    image = Image.new("RGB", (320, 320), "#eef3f8")
    draw = ImageDraw.Draw(image)
    draw.ellipse((40, 30, 280, 270), fill=shirt)
    draw.ellipse((92, 52, 228, 218), fill=skin)
    draw.pieslice((86, 34, 234, 150), 180, 360, fill=hair)
    draw.ellipse((128, 126, 146, 144), fill=eye)
    draw.ellipse((174, 126, 192, 144), fill=eye)
    draw.arc((142, 164, 182, 194), 10, 170, fill="#7a4a42", width=4)
    draw.ellipse((118, 180, 202, 246), fill=skin)
    image.save(path)


def main() -> None:
    SAMPLES.mkdir(parents=True, exist_ok=True)
    _avatar(SAMPLES / "face_a.png", skin="#f2c9a5", shirt="#4263eb", hair="#2b2118", eye="#2b2118")
    _avatar(SAMPLES / "face_b.png", skin="#d9a273", shirt="#2f9e44", hair="#1a1a1a", eye="#3b2f2f")
    Image.open(SAMPLES / "face_a.png").convert("RGB").save(SAMPLES / "face_a.jpg", quality=92)
    Image.new("RGB", (10, 10), "#ffffff").save(SAMPLES / "tiny.png")
    Image.new("RGB", (64, 64), "#d97706").save(SAMPLES / "sample.gif", format="GIF")
    (SAMPLES / "invalid.bin").write_bytes(b"this-is-not-an-image\x00\x01\x02")
    (SAMPLES / "oversized.bin").write_bytes(b"\x00" * (4 * 1024 * 1024 + 1))
    print(f"samples written to {SAMPLES}")


if __name__ == "__main__":
    main()
