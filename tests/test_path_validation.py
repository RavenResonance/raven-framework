# ================================================================
# Raven Framework — path / URL validation tests
# ================================================================

from __future__ import annotations

from pathlib import Path

import pytest

from raven_framework.helpers.security import (
    is_safe_media_url,
    is_valid_app_id,
    resolve_under_root,
)


@pytest.mark.parametrize(
    "app_id",
    ["my_app", "dev-app", "app123"],
)
def test_valid_app_ids(app_id: str) -> None:
    assert is_valid_app_id(app_id)


@pytest.mark.parametrize(
    "app_id",
    ["", "../escape", "foo/bar", "foo..bar", ".hidden", "a b"],
)
def test_invalid_app_ids(app_id: str) -> None:
    assert not is_valid_app_id(app_id)


def test_resolve_under_root_rejects_traversal(tmp_path: Path) -> None:
    root = tmp_path / "user_data"
    root.mkdir()
    with pytest.raises(ValueError):
        resolve_under_root(root, "../outside")


def test_resolve_under_root_ok(tmp_path: Path) -> None:
    root = tmp_path / "user_data"
    root.mkdir()
    resolved = resolve_under_root(root, "my_app")
    assert resolved == (root / "my_app").resolve()


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/image.png",
        "http://localhost/logo.png",
        "http://10.0.0.1/x",
        "http://192.168.1.1/x",
        "http://169.254.169.254/latest/meta-data/",
        "file:///etc/passwd",
        "ftp://example.com/x",
    ],
)
def test_unsafe_media_urls_blocked(url: str) -> None:
    assert is_safe_media_url(url) is False


def test_public_https_url_allowed() -> None:
    assert is_safe_media_url("https://example.com/image.png") is True


def test_unresolvable_host_blocked_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """DNS resolution failure must be treated as blocked, not allowed (fail closed)."""
    import raven_framework.helpers.security as security_module

    monkeypatch.setattr(security_module, "_resolve_host_ips", lambda hostname: [])
    assert is_safe_media_url("https://this-host-does-not-resolve.invalid/x") is False
