from __future__ import annotations


def test_epic9_exceptions_exist() -> None:
    from src.exceptions import (
        InvalidSlug,
        InviteAlreadyUsed,
        InviteExpired,
        InviteNotFound,
        MasterBlocked,
        ReservedSlug,
        SlugTaken,
    )

    assert issubclass(SlugTaken, Exception)
    assert issubclass(InvalidSlug, Exception)
    assert issubclass(ReservedSlug, Exception)
    assert issubclass(InviteNotFound, Exception)
    assert issubclass(InviteExpired, Exception)
    assert issubclass(InviteAlreadyUsed, Exception)
    assert issubclass(MasterBlocked, Exception)
