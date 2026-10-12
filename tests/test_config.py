"""Tests for configuration, model registry validation, and secret redaction."""
import pytest
from pydantic import ValidationError

from config.config import Settings, redact_secret, APPROVED_MODEL_IDS


def test_secret_redaction():
    assert redact_secret(None) == "[NOT CONFIGURED]"
    assert redact_secret("") == "[NOT CONFIGURED]"
    assert redact_secret("short") == "[REDACTED]"
    assert redact_secret("12345678") == "[REDACTED]"
    redacted = redact_secret("AIzaSyD-long-google-api-key-test")
    assert "AIza" in redacted
    assert "test" in redacted
    assert "long-google-api-key" not in redacted


def test_settings_repr_never_leaks_keys():
    test_key = "sk-super-secret-key-123456789"
    test_settings = Settings(
        nvidia_nim_api_key=test_key,
        google_api_key=test_key,
        qdrant_api_key=test_key,
    )
    repr_str = repr(test_settings)
    assert test_key not in repr_str
    safe = test_settings.safe_dict()
    assert test_key not in str(safe)
    assert safe["nvidia_nim_api_key"] != test_key
    assert safe["google_api_key"] != test_key
    assert safe["qdrant_api_key"] != test_key


def test_approved_models_registry():
    assert "gemini-3.1-flash-lite" in APPROVED_MODEL_IDS
    assert "gemma-4-26b-a4b-it" in APPROVED_MODEL_IDS
    assert "nvidia/nemotron-3-super-120b-a12b" in APPROVED_MODEL_IDS

    # Valid model succeeds
    s = Settings(model_decision="nvidia/nemotron-3-super-120b-a12b")
    assert s.model_decision == "nvidia/nemotron-3-super-120b-a12b"

    # Unapproved model fails validation
    with pytest.raises(ValidationError):
        Settings(model_decision="unapproved-model-id-xyz")


def test_settings_directories_exist():
    s = Settings()
    s.ensure_directories()
    assert s.reports_dir.exists()
    assert s.storage_dir.exists()
