# ================================================================
# Raven Framework — logger redaction tests
# ================================================================

from __future__ import annotations

from raven_framework.helpers.logger import redact_secrets


def test_redact_bearer_token() -> None:
    text = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abc.def"
    assert "[REDACTED]" in redact_secrets(text)
    assert "eyJhbGci" not in redact_secrets(text)


def test_redact_api_key_query_param() -> None:
    text = "url?api_key=supersecret123&foo=bar"
    redacted = redact_secrets(text)
    assert "supersecret123" not in redacted
    assert "[REDACTED]" in redacted


def test_redact_json_secret_field() -> None:
    text = '{"open_ai_key": "sk-test-value-here"}'
    redacted = redact_secrets(text)
    assert "sk-test" not in redacted


def test_redact_empty_string_unchanged() -> None:
    assert redact_secrets("") == ""


def test_redact_basic_auth_header() -> None:
    """The generic key=value pattern stops at the first whitespace, so
    "Authorization: Basic <creds>" previously only redacted the word
    "Basic" and left the actual credential in clear text."""
    text = "Authorization: Basic dXNlcjpwYXNz"
    redacted = redact_secrets(text)
    assert "dXNlcjpwYXNz" not in redacted
    assert "[REDACTED]" in redacted


def test_redact_digest_auth_header() -> None:
    text = "Authorization: Digest a1b2c3d4e5f6"
    redacted = redact_secrets(text)
    assert "a1b2c3d4e5f6" not in redacted
    assert "[REDACTED]" in redacted
