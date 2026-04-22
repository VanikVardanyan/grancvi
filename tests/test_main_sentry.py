from __future__ import annotations

from unittest.mock import MagicMock, patch


@patch("sentry_sdk.init")
def test_sentry_not_called_when_dsn_is_none(mock_init: MagicMock) -> None:
    from src.main import _init_sentry_if_configured

    _init_sentry_if_configured(dsn=None)

    mock_init.assert_not_called()


@patch("sentry_sdk.init")
def test_sentry_not_called_when_dsn_is_empty(mock_init: MagicMock) -> None:
    from src.main import _init_sentry_if_configured

    _init_sentry_if_configured(dsn="")

    mock_init.assert_not_called()


@patch("sentry_sdk.init")
def test_sentry_called_with_dsn(mock_init: MagicMock) -> None:
    from src.main import _init_sentry_if_configured

    _init_sentry_if_configured(dsn="https://public@sentry.io/1234")

    mock_init.assert_called_once()
    kwargs = mock_init.call_args.kwargs
    assert kwargs["dsn"] == "https://public@sentry.io/1234"
    assert kwargs["traces_sample_rate"] == 0.0
