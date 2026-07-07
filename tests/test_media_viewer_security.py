# ================================================================
# Raven Framework — MediaViewer URL security tests
# ================================================================

from __future__ import annotations

from raven_framework.helpers.security import is_safe_media_url


def test_media_viewer_blocks_loopback() -> None:
    assert is_safe_media_url("http://127.0.0.1/photo.jpg") is False


def test_media_viewer_blocks_metadata_ip() -> None:
    assert is_safe_media_url("http://169.254.169.254/") is False


def test_media_viewer_allows_public_host() -> None:
    # cdn.example.org doesn't resolve (example.org has no such subdomain);
    # www.example.com does, and is_safe_media_url resolves DNS to decide safety.
    assert is_safe_media_url("https://www.example.com/assets/logo.png") is True
