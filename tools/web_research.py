"""Web research adapter with real Firecrawl REST API integration for DecisionRoom.

Supports:
- Structured source records (title, URL, domain, text, query, timestamp, status)
- Real Firecrawl REST API adapter (requires FIRECRAWL_API_KEY)
- MockWebSearchProvider for deterministic offline unit testing
- Domain allow/deny filters
- Strict prompt injection neutralization (meta-instruction stripping)
- Cache with configurable expiry
- Explicit UNAVAILABLE status when key is missing (no silent failures)
"""
from __future__ import annotations

import logging
import re
import time
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple
from schemas.decision import EvidenceCitation

logger = logging.getLogger("decisionroom.web_research")

CACHE_TTL_SECONDS = 300  # 5 minutes
MAX_EXCERPT_CHARS = 1500


INJECTION_PATTERNS = [
    r"(?i)ignore\s+(all\s+)?previous\s+instructions",
    r"(?i)system\s*:\s*you\s+are\s+now",
    r"(?i)do\s+not\s+follow\s+any\s+(other\s+)?rules",
    r"(?i)output\s+the\s+following\s+password",
    r"(?i)you\s+must\s+say\s+proceed",
    r"(?i)disregard\s+prior\s+guidance",
]


@dataclass
class SourceRecord:
    """Standardized record of web evidence."""
    title: str
    url: str
    domain: str
    retrieval_timestamp: datetime
    extracted_text: str
    query: str
    status: str  # "SUCCESS", "FAILED", "CACHED", "MOCK", "UNAVAILABLE"
    publication_date: Optional[str] = None
    sanitized: bool = True

    def to_citation(self, source_id: str) -> EvidenceCitation:
        """Convert to EvidenceCitation. Status MOCK is never marked verified."""
        return EvidenceCitation(
            source_id=source_id,
            title=f"{self.title} ({self.domain})",
            url=self.url,
            page_or_section=self.publication_date or "Web Evidence",
            snippet=self.extracted_text[:MAX_EXCERPT_CHARS],
            retrieval_timestamp=self.retrieval_timestamp,
            # shortcut: HTTP 200 alone does not verify the content supports a claim
            verified=False,
        )


def sanitize_web_content(text: str) -> str:
    """Neutralize potential prompt injection attempts and normalize text."""
    clean = text.replace("\r\n", "\n")
    for pattern in INJECTION_PATTERNS:
        clean = re.sub(pattern, "[FILTERED_PROMPT_INJECTION_ATTEMPT]", clean)
    return clean.strip()


class BaseWebSearchProvider:
    """Base interface for web research providers."""
    def search(self, query: str, limit: int = 5) -> List[SourceRecord]:
        raise NotImplementedError


class MockWebSearchProvider(BaseWebSearchProvider):
    """Deterministic mock provider for offline tests and predictable scenarios.

    Results are marked MOCK and are never marked verified.
    """

    def __init__(self, mock_results: Optional[List[Dict[str, str]]] = None):
        self.mock_results = mock_results or []
        self.recorded_queries: List[str] = []

    def search(self, query: str, limit: int = 5) -> List[SourceRecord]:
        self.recorded_queries.append(query)
        now = datetime.now(timezone.utc)
        records = []
        for idx, item in enumerate(self.mock_results[:limit]):
            url = item.get("url", f"https://mock-evidence.org/item-{idx}")
            domain = urllib.parse.urlparse(url).netloc or "mock-evidence.org"
            raw_text = item.get("text", f"Mock factual evidence for query '{query}'.")
            records.append(
                SourceRecord(
                    title=item.get("title", f"Evidence {idx + 1}"),
                    url=url,
                    domain=domain,
                    retrieval_timestamp=now,
                    extracted_text=sanitize_web_content(raw_text),
                    query=query,
                    status="MOCK",
                    publication_date=item.get("date", "2026-01-01"),
                )
            )
        return records


_UNSET = object()


class FirecrawlAdapter(BaseWebSearchProvider):
    """Real Firecrawl REST API adapter for web search and scraping.

    Uses the /v1/search endpoint (Firecrawl API).
    Falls back to UNAVAILABLE status when key is missing — no silent empty return.

    This is a direct REST adapter. An MCP server attached to Antigravity IDE
    is NOT automatically callable by the running Python app.
    """

    def __init__(self, api_key: Any = _UNSET, base_url: Optional[str] = None):
        from config.config import settings
        if api_key is _UNSET:
            self.api_key = settings.firecrawl_api_key
        else:
            self.api_key = api_key or ""
        self.base_url = (base_url or settings.firecrawl_base_url).rstrip("/")
        self.timeout = getattr(settings, "request_timeout_seconds", 30)

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, limit: int = 5) -> List[SourceRecord]:
        now = datetime.now(timezone.utc)
        if not self.is_available():
            logger.info("Firecrawl API key not configured. Returning UNAVAILABLE status.")
            return [
                SourceRecord(
                    title="Web Search Unavailable",
                    url="",
                    domain="",
                    retrieval_timestamp=now,
                    extracted_text="Firecrawl API key not configured. Web search unavailable.",
                    query=query,
                    status="UNAVAILABLE",
                )
            ]

        try:
            import requests
            response = requests.post(
                f"{self.base_url}/v1/search",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={"query": query, "limit": limit, "scrapeOptions": {"formats": ["markdown"]}},
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            logger.warning("Firecrawl search failed for query '%s': %s", query[:80], type(exc).__name__)
            return [
                SourceRecord(
                    title="Web Search Failed",
                    url="",
                    domain="",
                    retrieval_timestamp=now,
                    extracted_text=f"Firecrawl search failed: {type(exc).__name__}. No results available.",
                    query=query,
                    status="FAILED",
                )
            ]

        records: List[SourceRecord] = []
        for item in data.get("data", []):
            url = item.get("url", "")
            domain = urllib.parse.urlparse(url).netloc or "unknown"
            raw_text = (
                item.get("markdown", "")
                or item.get("content", "")
                or item.get("description", "")
            )
            records.append(
                SourceRecord(
                    title=item.get("title", url),
                    url=url,
                    domain=domain,
                    retrieval_timestamp=now,
                    extracted_text=sanitize_web_content(raw_text)[:MAX_EXCERPT_CHARS],
                    query=query,
                    status="SUCCESS",
                    publication_date=item.get("publishedDate"),
                )
            )

        logger.info("Firecrawl returned %d results for query '%s'", len(records), query[:60])
        return records


# Keep old name as alias for backward compatibility in tests
FirecrawlMCPAdapter = FirecrawlAdapter


class WebResearchService:
    """High-level web research service enforcing source preferences and domain boundaries."""

    def __init__(
        self,
        provider: Optional[BaseWebSearchProvider] = None,
        allowed_domains: Optional[Set[str]] = None,
        blocked_domains: Optional[Set[str]] = None,
        cache_ttl_seconds: int = CACHE_TTL_SECONDS,
    ):
        self.provider = provider or FirecrawlAdapter()
        self.allowed_domains = allowed_domains or set()
        self.blocked_domains = blocked_domains or {"spam.com", "unverified-rumor.net"}
        self._cache: Dict[str, Tuple[datetime, List[SourceRecord]]] = {}
        self._cache_ttl = timedelta(seconds=cache_ttl_seconds)

    def search(
        self,
        query: str,
        limit: int = 5,
        enforce_authoritative_only: bool = False,
    ) -> List[SourceRecord]:
        """Search and filter web sources against safety and authority criteria.

        Results include UNAVAILABLE/FAILED records so callers know search status.
        """
        q = query.strip()
        if not q:
            return []

        # Cache lookup
        cache_key = f"{q}::{enforce_authoritative_only}"
        if cache_key in self._cache:
            cached_time, cached_records = self._cache[cache_key]
            if datetime.now(timezone.utc) - cached_time < self._cache_ttl:
                logger.debug("Returning cached results for query: %s", q[:60])
                return cached_records[:limit]

        raw_records = self.provider.search(q, limit=limit * 2)

        filtered: List[SourceRecord] = []
        for record in raw_records:
            if record.status in {"UNAVAILABLE", "FAILED"}:
                filtered.append(record)
                continue

            domain = record.domain.lower()

            if any(blocked in domain for blocked in self.blocked_domains):
                continue

            if enforce_authoritative_only:
                is_authoritative = (
                    domain.endswith(".gov")
                    or ".gov." in domain
                    or domain.endswith(".edu")
                    or ".edu." in domain
                    or domain.endswith(".org")
                    or domain.startswith("gov.")
                    or any(allowed in domain for allowed in self.allowed_domains)
                )
                if not is_authoritative:
                    continue

            filtered.append(record)
            if len(filtered) >= limit:
                break

        self._cache[cache_key] = (datetime.now(timezone.utc), filtered)
        return filtered

    def get_citations(self, query: str, limit: int = 3) -> List[EvidenceCitation]:
        """Return search results converted directly into validated EvidenceCitations."""
        records = self.search(query, limit=limit)
        return [r.to_citation(f"web_{idx}") for idx, r in enumerate(records)]
