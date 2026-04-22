from __future__ import annotations

from uuid import uuid4

from src.callback_data.admin import AdminMasterCallback, BlockCallback
from src.callback_data.catalog import CatalogMasterCallback
from src.callback_data.registration import SlugConfirmCallback, SpecialtyHintCallback


def test_specialty_hint_pack_unpack() -> None:
    cb = SpecialtyHintCallback(hint="hair")
    packed = cb.pack()
    unpacked = SpecialtyHintCallback.unpack(packed)
    assert unpacked.hint == "hair"


def test_slug_confirm_pack_unpack() -> None:
    for action in ("use", "change"):
        cb = SlugConfirmCallback(action=action)
        unpacked = SlugConfirmCallback.unpack(cb.pack())
        assert unpacked.action == action


def test_admin_master_pack_unpack() -> None:
    mid = uuid4()
    cb = AdminMasterCallback(master_id=mid, action="view")
    u = AdminMasterCallback.unpack(cb.pack())
    assert u.master_id == mid and u.action == "view"


def test_block_callback() -> None:
    mid = uuid4()
    cb = BlockCallback(master_id=mid, block=True)
    u = BlockCallback.unpack(cb.pack())
    assert u.master_id == mid and u.block is True


def test_catalog_master_callback() -> None:
    mid = uuid4()
    cb = CatalogMasterCallback(master_id=mid)
    u = CatalogMasterCallback.unpack(cb.pack())
    assert u.master_id == mid
