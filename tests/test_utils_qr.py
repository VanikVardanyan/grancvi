from __future__ import annotations

from src.utils.qr import build_master_qr


def test_build_master_qr_returns_png_bytes() -> None:
    png = build_master_qr("https://t.me/GrancviBot?start=master_anna-7f3c")
    assert isinstance(png, bytes)
    assert png[:8] == b"\x89PNG\r\n\x1a\n", "must be a valid PNG file"
    assert len(png) > 200, "QR PNG should be at least a couple hundred bytes"


def test_build_master_qr_different_urls_produce_different_images() -> None:
    png_a = build_master_qr("https://t.me/Bot?start=master_aaa")
    png_b = build_master_qr("https://t.me/Bot?start=master_bbb")
    assert png_a != png_b
