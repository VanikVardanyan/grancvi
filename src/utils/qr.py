from __future__ import annotations

import io

import segno


def build_master_qr(url: str) -> bytes:
    """Render a master's deep-link URL as a PNG QR code.

    Uses error correction level M (15%) — enough to survive light smudging on
    a printed sticker without making the code unnecessarily dense.
    """
    qr = segno.make(url, error="m")
    buffer = io.BytesIO()
    qr.save(buffer, kind="png", scale=10, border=2)
    return buffer.getvalue()
