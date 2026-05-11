from __future__ import annotations

import io
import os
import uuid
from pathlib import Path
from typing import Final

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

from src.exceptions import BadImage

register_heif_opener()


_TARGET_SIZE: Final = 256
_JPEG_QUALITY: Final = 85


def process_image(raw: bytes) -> bytes:
    """Decode arbitrary image bytes, return a 256x256 JPEG.

    Steps: validate → EXIF orient → center-crop to square → resize → JPEG q=85.
    """
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            probe.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise BadImage(str(exc)) from exc

    try:
        opened: Image.Image = Image.open(io.BytesIO(raw))
        img: Image.Image = ImageOps.exif_transpose(opened) or opened
        if img.mode != "RGB":
            img = img.convert("RGB")
        side = min(img.size)
        left = (img.size[0] - side) // 2
        top = (img.size[1] - side) // 2
        img = img.crop((left, top, left + side, top + side))
        img = img.resize((_TARGET_SIZE, _TARGET_SIZE), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
        return out.getvalue()
    except (OSError, ValueError) as exc:
        raise BadImage(str(exc)) from exc


class AvatarService:
    """Filesystem persistence for master avatars.

    One JPEG per master, named ``<master_id>.jpg`` under ``directory``.
    Writes are atomic: temp file in the same directory, then ``os.replace``.
    """

    def __init__(self, directory: str) -> None:
        self._dir = Path(directory)

    def path_for(self, master_id: uuid.UUID) -> Path:
        return self._dir / f"{master_id}.jpg"

    def save(self, master_id: uuid.UUID, raw: bytes) -> None:
        processed = process_image(raw)
        self._dir.mkdir(parents=True, exist_ok=True)
        target = self.path_for(master_id)
        tmp = target.with_suffix(".jpg.tmp")
        tmp.write_bytes(processed)
        os.replace(tmp, target)

    def delete(self, master_id: uuid.UUID) -> None:
        self.path_for(master_id).unlink(missing_ok=True)
