"""Tests for bonfires.sdk.http."""

from unittest.mock import MagicMock, patch

import pytest

from bonfires.sdk.config import BonfiresConfig
from bonfires.sdk.exceptions import APIError, AuthenticationError, NotFoundError
from bonfires.sdk.http import _get, _post


@pytest.fixture()
def cfg(tmp_path):
    return BonfiresConfig(
        api_key="test-key",
        bonfire_id="bf-1",
        agent_id="ag-1",
        vault_dir=str(tmp_path),
    )


@patch("bonfires.sdk.http.requests.post")
def test_post_success(mock_post, cfg):
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"result": "ok"}
    mock_post.return_value = mock_resp

    result = _post(cfg, "/test", {"key": "val"})
    assert result == {"result": "ok"}
    mock_post.assert_called_once()


@patch("bonfires.sdk.http.requests.post")
def test_post_404_raises_not_found(mock_post, cfg):
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 404
    mock_resp.text = "not found"
    mock_post.return_value = mock_resp

    with pytest.raises(NotFoundError) as exc_info:
        _post(cfg, "/test", {})
    assert exc_info.value.status_code == 404


@patch("bonfires.sdk.http.requests.post")
def test_post_401_raises_auth_error(mock_post, cfg):
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 401
    mock_resp.text = "unauthorized"
    mock_post.return_value = mock_resp

    with pytest.raises(AuthenticationError):
        _post(cfg, "/test", {})


@patch("bonfires.sdk.http.requests.post")
def test_post_500_raises_api_error(mock_post, cfg):
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 500
    mock_resp.text = "internal error"
    mock_post.return_value = mock_resp

    with pytest.raises(APIError) as exc_info:
        _post(cfg, "/test", {})
    assert exc_info.value.status_code == 500


@patch("bonfires.sdk.http.requests.post")
def test_post_connection_error(mock_post, cfg):
    import requests

    mock_post.side_effect = requests.ConnectionError("fail")

    with pytest.raises(APIError, match="Connection error"):
        _post(cfg, "/test", {})


@patch("bonfires.sdk.http.requests.get")
def test_get_success(mock_get, cfg):
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"data": [1, 2]}
    mock_get.return_value = mock_resp

    result = _get(cfg, "/test", params={"q": "hello"})
    assert result == {"data": [1, 2]}


@patch("bonfires.sdk.http.requests.get")
def test_get_404(mock_get, cfg):
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 404
    mock_resp.text = "not found"
    mock_get.return_value = mock_resp

    with pytest.raises(NotFoundError):
        _get(cfg, "/missing")
