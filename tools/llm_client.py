"""Provider-independent LLM client abstraction for DecisionRoom.

Supports:
- NVIDIA NIM hosted models (e.g. nvidia/nemotron-3-super-120b-a12b) via OpenAI-compatible API
- Google Gemini & Gemma models (e.g. gemini-3.1-flash-lite, gemma-4-26b-a4b-it)
- Mock provider for reliable, deterministic offline testing

Never prints secrets in error messages or logs. Validates against APPROVED_MODEL_IDS.
"""
from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type, TypeVar
from pydantic import BaseModel

from config.config import settings, APPROVED_MODEL_IDS, redact_secret

logger = logging.getLogger("decisionroom.llm")
T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Base exception for all LLM client errors."""
    pass


class ProviderNotConfiguredError(LLMError):
    """Raised when an API key or endpoint for a requested provider is missing."""
    pass


class ModelNotApprovedError(LLMError):
    """Raised when a model is not in the explicit approved registry."""
    pass


class StructuredOutputError(LLMError):
    """Raised when an LLM fails to return valid schema-matching JSON."""
    pass


class BaseLLMProvider(ABC):
    """Abstract interface for LLM providers."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 1500,
    ) -> str:
        """Generate text completion from provider."""
        pass


class MockLLMProvider(BaseLLMProvider):
    """Deterministic mock provider for offline tests and simulations."""

    def __init__(self, canned_response: Optional[str] = None):
        self.canned_response = canned_response or "Mock LLM output for testing."
        self.call_history: list[dict] = []

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 1500,
    ) -> str:
        self.call_history.append({
            "prompt": prompt,
            "system_prompt": system_prompt,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })
        return self.canned_response


class NvidiaNimProvider(BaseLLMProvider):
    """NVIDIA NIM hosted API client (OpenAI API-compatible)."""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = settings.nvidia_nim_api_key if api_key is None else api_key
        self.base_url = settings.nvidia_nim_base_url if base_url is None else base_url
        self._client: Any = None

    def _get_client(self) -> Any:
        if not self.api_key:
            raise ProviderNotConfiguredError(
                "NVIDIA NIM API key is not configured. Set NVIDIA_NIM_API_KEY in .env"
            )
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    timeout=settings.request_timeout_seconds,
                    max_retries=settings.max_retries,
                )
            except ImportError as exc:
                raise LLMError(f"OpenAI package required for NVIDIA NIM: {exc}") from exc
        return self._client

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 1500,
    ) -> str:
        client = self._get_client()
        target_model = model or settings.model_decision

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = client.chat.completions.create(
                model=target_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"} if "json" in (system_prompt or "").lower() else None,
            )
            content = response.choices[0].message.content
            if not content:
                raise LLMError("NVIDIA NIM returned an empty response.")
            return content.strip()
        except Exception as exc:
            # Redact any accidental key leakage in exception messages
            clean_msg = str(exc).replace(self.api_key, redact_secret(self.api_key))
            raise LLMError(f"NVIDIA NIM call failed for model {target_model}: {clean_msg}") from exc


class GoogleGenAIProvider(BaseLLMProvider):
    """Google Gemini & Gemma models via Google GenAI SDK."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = settings.google_api_key if api_key is None else api_key
        self._client: Any = None

    def _get_client(self) -> Any:
        if not self.api_key:
            raise ProviderNotConfiguredError(
                "Google GenAI API key is not configured. Set GOOGLE_API_KEY in .env"
            )
        if self._client is None:
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            except ImportError as exc:
                raise LLMError(f"google-genai package required for Google models: {exc}") from exc
        return self._client

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 1500,
    ) -> str:
        client = self._get_client()
        target_model = model or settings.model_intake

        full_prompt = f"System: {system_prompt}\n\nUser: {prompt}" if system_prompt else prompt

        try:
            response = client.models.generate_content(
                model=target_model,
                contents=full_prompt,
                config={
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                },
            )
            raw_text = getattr(response, "text", None) or ""
            if not raw_text.strip():
                raise LLMError("Google GenAI returned an empty response.")
            return raw_text.strip()
        except Exception as exc:
            clean_msg = str(exc).replace(self.api_key, redact_secret(self.api_key))
            raise LLMError(f"Google GenAI call failed for model {target_model}: {clean_msg}") from exc


class LLMClient:
    """Unified client orchestrating routing, validation, retries, and structured parsing."""

    def __init__(self, provider: Optional[BaseLLMProvider] = None):
        self._custom_provider = provider
        self._nvidia_provider = NvidiaNimProvider()
        self._google_provider = GoogleGenAIProvider()

    def route_provider(self, model_id: str) -> BaseLLMProvider:
        """Route to appropriate provider based on model ID prefix or explicit configuration."""
        if self._custom_provider:
            return self._custom_provider

        if model_id.startswith("nvidia/"):
            return self._nvidia_provider
        elif model_id.startswith(("gemini", "gemma")):
            return self._google_provider
        else:
            # Fallback to configured default provider
            if settings.default_llm_provider == "google":
                return self._google_provider
            return self._nvidia_provider

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 1500,
    ) -> str:
        target_model = model or settings.model_decision
        if target_model not in APPROVED_MODEL_IDS:
            raise ModelNotApprovedError(
                f"Model '{target_model}' is not approved. Valid models: {sorted(APPROVED_MODEL_IDS)}"
            )

        provider = self.route_provider(target_model)
        return provider.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            model=target_model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.1,
    ) -> T:
        """Generate and validate a structured response against a Pydantic schema."""
        json_directive = (
            f"\nYou must return ONLY a single valid JSON object matching this schema:\n"
            f"{json.dumps(response_model.model_json_schema(), indent=2)}\n"
            f"Do not include any Markdown fences (e.g. ```json), explanations, or text outside the JSON object."
        )
        combined_sys = (system_prompt or "") + "\n" + json_directive

        raw_output = self.generate(
            prompt=prompt,
            system_prompt=combined_sys,
            model=model,
            temperature=temperature,
            max_tokens=2000,
        )

        # Clean potential markdown fences if present
        clean_json = raw_output.strip()
        if clean_json.startswith("```"):
            lines = clean_json.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            clean_json = "\n".join(lines).strip()

        try:
            parsed = json.loads(clean_json)
            return response_model.model_validate(parsed)
        except Exception as exc:
            raise StructuredOutputError(
                f"Failed to parse structured output into {response_model.__name__}: {exc}\nRaw: {raw_output[:300]}"
            ) from exc
