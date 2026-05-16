from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.db.models import Master


def avatar_url_for(master: Master) -> str | None:
    """Public static URL for a master's avatar, or None when unset.

    Single source of truth for the avatar URL contract: a host-relative
    path under the StaticFiles mount, cache-busted by the upload time.
    """
    if master.avatar_uploaded_at is None:
        return None
    return f"/static/avatars/{master.id}.jpg?v={int(master.avatar_uploaded_at.timestamp())}"
