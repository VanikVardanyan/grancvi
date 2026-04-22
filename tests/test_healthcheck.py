from __future__ import annotations

import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest


def _fake_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    resp.read = MagicMock(return_value=json.dumps(payload).encode())
    return resp


def test_healthcheck_no_token(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("BOT_TOKEN", raising=False)

    from scripts.healthcheck import main

    rc = main()

    assert rc == 1
    assert "BOT_TOKEN not set" in capsys.readouterr().err


def test_healthcheck_empty_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "")

    from scripts.healthcheck import main

    assert main() == 1


@patch("urllib.request.urlopen")
def test_healthcheck_success(mock_open: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "dummy")
    mock_open.return_value = _fake_response({"ok": True, "result": {"id": 1}})

    from scripts.healthcheck import main

    assert main() == 0


@patch("urllib.request.urlopen")
def test_healthcheck_telegram_ok_false(
    mock_open: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BOT_TOKEN", "dummy")
    mock_open.return_value = _fake_response({"ok": False, "description": "bad"})

    from scripts.healthcheck import main

    assert main() == 1


@patch("urllib.request.urlopen")
def test_healthcheck_network_error(
    mock_open: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("BOT_TOKEN", "dummy")
    mock_open.side_effect = urllib.error.URLError("unreachable")

    from scripts.healthcheck import main

    assert main() == 1
    assert "getMe failed" in capsys.readouterr().err


@patch("urllib.request.urlopen")
def test_healthcheck_timeout(
    mock_open: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("BOT_TOKEN", "dummy")
    mock_open.side_effect = TimeoutError("too slow")

    from scripts.healthcheck import main

    assert main() == 1
    assert "timed out" in capsys.readouterr().err


@patch("urllib.request.urlopen")
def test_healthcheck_non_json(mock_open: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "dummy")
    resp = MagicMock()
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    resp.read = MagicMock(return_value=b"<html>error</html>")
    mock_open.return_value = resp

    from scripts.healthcheck import main

    assert main() == 1
