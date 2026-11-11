"""Las imágenes de marca locales (Home Assistant 2026.3+) existen y tienen el tamaño esperado."""

import struct
from pathlib import Path

BRAND = Path(__file__).resolve().parents[1] / "custom_components" / "factusol" / "brand"


def _size(name: str) -> tuple[int, int]:
    data = (BRAND / name).read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


def test_icons():
    assert _size("icon.png") == (256, 256)
    assert _size("icon@2x.png") == (512, 512)


def test_logos():
    w, h = _size("logo.png")
    assert h == 256 and w > h
    assert _size("logo@2x.png") == (w * 2, h * 2)
