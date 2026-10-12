"""Tests for LLMClient, mock provider, model routing, and error handling."""
import pytest
from pydantic import BaseModel

from tools.llm_client import (
    LLMClient,
    MockLLMProvider,
    ModelNotApprovedError,
    ProviderNotConfiguredError,
    StructuredOutputError,
    NvidiaNimProvider,
    GoogleGenAIProvider,
)


class SampleSchema(BaseModel):
    decision: str
    rationale: str
    confidence_score: float


def test_mock_provider_generation():
    mock = MockLLMProvider("Mock completion output")
    client = LLMClient(provider=mock)
    res = client.generate("hello", model="gemini-3.1-flash-lite")
    assert res == "Mock completion output"
    assert len(mock.call_history) == 1
    assert mock.call_history[0]["prompt"] == "hello"


def test_mock_provider_structured_output():
    json_data = '{"decision": "PROCEED", "rationale": "High ROI", "confidence_score": 0.92}'
    mock = MockLLMProvider(json_data)
    client = LLMClient(provider=mock)
    parsed = client.generate_structured("prompt", response_model=SampleSchema, model="gemini-3.1-flash-lite")
    assert parsed.decision == "PROCEED"
    assert parsed.rationale == "High ROI"
    assert parsed.confidence_score == 0.92


def test_unapproved_model_rejected():
    client = LLMClient(provider=MockLLMProvider())
    with pytest.raises(ModelNotApprovedError):
        client.generate("hello", model="non-existent-gpt-model")


def test_malformed_json_raises_structured_output_error():
    mock = MockLLMProvider("This is not JSON text at all.")
    client = LLMClient(provider=mock)
    with pytest.raises(StructuredOutputError):
        client.generate_structured("prompt", response_model=SampleSchema, model="gemini-3.1-flash-lite")


def test_unconfigured_provider_raises_clean_error():
    unconfigured_nvidia = NvidiaNimProvider(api_key="")
    with pytest.raises(ProviderNotConfiguredError):
        unconfigured_nvidia.generate("test", model="nvidia/nemotron-3-super-120b-a12b")

    unconfigured_google = GoogleGenAIProvider(api_key="")
    with pytest.raises(ProviderNotConfiguredError):
        unconfigured_google.generate("test", model="gemini-3.1-flash-lite")
