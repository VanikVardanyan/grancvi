from __future__ import annotations

from uuid import uuid4

from src.callback_data.approval import ApprovalCallback
from src.callback_data.master_add import (
    CustomTimeCallback,
    PhoneDupCallback,
    RecentClientCallback,
    SkipCommentCallback,
)


def test_recent_client_with_uuid_roundtrip() -> None:
    cid = uuid4()
    packed = RecentClientCallback(client_id=str(cid)).pack()
    assert packed.startswith("mac:")
    parsed = RecentClientCallback.unpack(packed)
    assert parsed.client_id == str(cid)


def test_recent_client_special_tokens_roundtrip() -> None:
    assert (
        RecentClientCallback.unpack(RecentClientCallback(client_id="new").pack()).client_id == "new"
    )
    assert (
        RecentClientCallback.unpack(RecentClientCallback(client_id="search").pack()).client_id
        == "search"
    )


def test_phone_dup_roundtrip() -> None:
    cid = uuid4()
    for action in ("use", "retry"):
        packed = PhoneDupCallback(action=action, client_id=cid).pack()  # type: ignore[arg-type]
        assert packed.startswith("mdp:")
        parsed = PhoneDupCallback.unpack(packed)
        assert parsed.action == action
        assert parsed.client_id == cid


def test_skip_comment_roundtrip() -> None:
    assert SkipCommentCallback.unpack(SkipCommentCallback().pack()).__class__ is SkipCommentCallback


def test_custom_time_roundtrip() -> None:
    assert CustomTimeCallback.unpack(CustomTimeCallback().pack()).__class__ is CustomTimeCallback


def test_approval_callback_supports_cancel() -> None:
    cid = uuid4()
    packed = ApprovalCallback(action="cancel", appointment_id=cid).pack()
    parsed = ApprovalCallback.unpack(packed)
    assert parsed.action == "cancel"
    assert parsed.appointment_id == cid
