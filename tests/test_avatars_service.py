from __future__ import annotations

import io
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image

from src.exceptions import BadImage
from src.services.avatars import AvatarService, process_image


def _jpeg_bytes(width: int, height: int, color: tuple[int, int, int] = (10, 100, 200)) -> bytes:
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _png_bytes_with_alpha(size: int = 800) -> bytes:
    img = Image.new("RGBA", (size, size), (10, 100, 200, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _heic_bytes(size: int = 1200) -> bytes:
    img = Image.new("RGB", (size, size), (200, 50, 50))
    buf = io.BytesIO()
    img.save(buf, format="HEIF", quality=80)
    return buf.getvalue()


def test_process_image_landscape_jpeg_to_256x256() -> None:
    raw = _jpeg_bytes(3000, 2000)
    out = process_image(raw)
    img = Image.open(io.BytesIO(out))
    assert img.format == "JPEG"
    assert img.size == (256, 256)
    assert len(out) <= 60_000


def test_process_image_portrait_jpeg_to_256x256() -> None:
    raw = _jpeg_bytes(800, 1600)
    out = process_image(raw)
    img = Image.open(io.BytesIO(out))
    assert img.size == (256, 256)


def test_process_image_png_with_alpha_returns_jpeg() -> None:
    raw = _png_bytes_with_alpha()
    out = process_image(raw)
    img = Image.open(io.BytesIO(out))
    assert img.format == "JPEG"
    assert img.size == (256, 256)
    assert img.mode == "RGB"


def test_process_image_heic_decodes() -> None:
    raw = _heic_bytes()
    out = process_image(raw)
    img = Image.open(io.BytesIO(out))
    assert img.format == "JPEG"
    assert img.size == (256, 256)


def test_process_image_garbage_raises_bad_image() -> None:
    with pytest.raises(BadImage):
        process_image(b"definitely not an image")


def test_save_writes_file_atomically(tmp_path: Path) -> None:
    svc = AvatarService(directory=str(tmp_path))
    master_id = uuid4()
    svc.save(master_id, _jpeg_bytes(900, 900))
    target = tmp_path / f"{master_id}.jpg"
    assert target.exists()
    img = Image.open(target)
    assert img.size == (256, 256)


def test_save_overwrites_existing(tmp_path: Path) -> None:
    svc = AvatarService(directory=str(tmp_path))
    master_id = uuid4()
    svc.save(master_id, _jpeg_bytes(900, 900, color=(255, 0, 0)))
    first_size = (tmp_path / f"{master_id}.jpg").stat().st_size
    svc.save(master_id, _jpeg_bytes(900, 900, color=(0, 0, 255)))
    second_size = (tmp_path / f"{master_id}.jpg").stat().st_size
    assert second_size > 0
    assert first_size > 0


def test_delete_removes_file(tmp_path: Path) -> None:
    svc = AvatarService(directory=str(tmp_path))
    master_id = uuid4()
    svc.save(master_id, _jpeg_bytes(900, 900))
    svc.delete(master_id)
    assert not (tmp_path / f"{master_id}.jpg").exists()


def test_delete_missing_is_noop(tmp_path: Path) -> None:
    svc = AvatarService(directory=str(tmp_path))
    svc.delete(uuid4())  # should not raise


def test_path_for_returns_expected_filename(tmp_path: Path) -> None:
    svc = AvatarService(directory=str(tmp_path))
    master_id = uuid4()
    assert svc.path_for(master_id) == tmp_path / f"{master_id}.jpg"
