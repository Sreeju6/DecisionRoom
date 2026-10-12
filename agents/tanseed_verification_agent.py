"""Evidence-aware live-source verification for DecisionRoom's TANSEED workflow.

Checks official StartupTN/TANFUND and Tamil Nadu government source pages,
records redirects/status/errors, and extracts limited application/deadline signals.
It never treats reachability or generic 'Apply' text as proof that a round is open.
Uses only the Python standard library.
"""
from __future__ import annotations

from datetime import datetime, timezone, date
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import re

# Prefer official programme/application pages and government announcements.
# The press-release URL is a historical official announcement, not evidence of
# a currently open application round.
SOURCES = [
    {"name": "StartupTN main website", "url": "https://startuptn.in/", "kind": "official portal", "official": True},
    {"name": "StartupTN TANSEED programme page (may have moved)", "url": "https://startuptn.in/initiative/funding/tanseed", "kind": "programme page", "official": True},
    {"name": "StartupTN TANSEED application portal", "url": "https://form.startuptn.in/tanseed", "kind": "application portal", "official": True},
    {"name": "TANFUND portal", "url": "https://www.tanfund.in/", "kind": "funding portal", "official": True},
    {"name": "Startup India Tamil Nadu policy listing", "url": "https://www.startupindia.gov.in/content/sih/en/state-startup-policies/Tamil-Nadu-state-policy.html", "kind": "policy listing", "official": True},
    {"name": "StartupTN 2023 policy PDF", "url": "https://startuptn.in/pdf/Tamil-Nadu-Startup-and-Innovation-Policy-2023.pdf", "kind": "historical policy", "official": True},
]

# A dated official announcement is useful as historical context only. It is NOT
# proof that a new round is open. Never convert this historical evidence to OPEN.
HISTORICAL_ROUNDS = [
    {"edition": "TANSEED 8.0", "reported_deadline": "2025-12-20",
     "source_url": "https://www.linkedin.com/posts/thestartuptn_startuptn-tanseed-seedfunding-activity-7403007179018215424-shKM",
     "note": "Dated announcement; historical deadline, not a current application window."},
]

USER_AGENT = "DecisionRoom/1.1 (public-source verification; educational project)"
MAX_BYTES = 1_000_000
TIMEOUT_SECONDS = 7


class _VisibleTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"script", "style", "noscript", "svg", "template"}:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in {"script", "style", "noscript", "svg", "template"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if not self._skip_depth and data and data.strip():
            self.parts.append(data.strip())


def _fetch(url: str) -> dict:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf,*/*"})
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            status = getattr(response, "status", 200)
            content_type = response.headers.get("Content-Type", "")
            final_url = response.geturl()
            body = response.read(MAX_BYTES)
            page_text = ""
            if "html" in content_type.casefold() or body.lstrip().lower().startswith((b"<!doctype html", b"<html")):
                parser = _VisibleTextParser()
                parser.feed(body.decode("utf-8", errors="replace"))
                page_text = " ".join(parser.parts)
            elif "text/plain" in content_type.casefold():
                page_text = body.decode("utf-8", errors="replace")
            return {
                "requested_url": url,
                "final_url": final_url,
                "http_status": status,
                "reachable": 200 <= status < 400,
                "content_type": content_type,
                "error": None,
                "page_text": re.sub(r"\s+", " ", page_text).strip(),
            }
    except HTTPError as exc:
        return {"requested_url": url, "final_url": exc.geturl(), "http_status": exc.code,
                "reachable": False, "content_type": exc.headers.get("Content-Type", "") if exc.headers else "",
                "error": f"HTTP {exc.code}", "page_text": ""}
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        reason = getattr(exc, "reason", exc)
        return {"requested_url": url, "final_url": None, "http_status": None,
                "reachable": False, "content_type": "", "error": f"{type(reason).__name__}: {reason}",
                "page_text": ""}


def _extract_deadline_signals(text: str) -> list[str]:
    """Return bounded text snippets around deadline/application phrases."""
    signals = []
    patterns = [
        r".{0,100}(?:last date|deadline|closes? on|extended till|extended until).{0,130}",
        r".{0,100}(?:applications? (?:are )?open|inviting applications|apply now).{0,130}",
        r".{0,100}(?:TANSEED\s*[0-9.]+).{0,100}",
    ]
    normalized = re.sub(r"\s+", " ", text)
    for pattern in patterns:
        for match in re.finditer(pattern, normalized, flags=re.IGNORECASE):
            snippet = re.sub(r"\s+", " ", match.group(0)).strip(" .;:-")
            if snippet and snippet not in signals:
                signals.append(snippet[:240])
            if len(signals) >= 8:
                return signals
    return signals


def _programme_signals(text: str, kind: str) -> list[str]:
    """Only TANSEED-specific local passages, never generic Apply Now banners."""
    if not text or kind == "historical policy":
        return []
    normalized = re.sub(r"\s+", " ", text)
    snippets = []
    for match in re.finditer(r"\btanseed\b", normalized, re.I):
        window = normalized[max(0, match.start()-110):match.end()+210]
        if re.search(r"deadline|last date|apply|applications|open|closed|\b[0-9]+\.0\b", window, re.I):
            if window not in snippets:
                snippets.append(window[:320])
        if len(snippets) == 5:
            break
    return snippets


def verify_tanseed_sources() -> dict:
    """Bounded live checks, explicit provenance, and conservative status."""
    checked_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    checked_sources = []
    for source in SOURCES:
        fetched = _fetch(source["url"])
        body_text = fetched.pop("page_text", "")
        signals = _programme_signals(body_text, source["kind"])
        checked_sources.append({
            **source,
            "http_status": fetched["http_status"],
            "reachable": fetched["reachable"],
            "final_url": fetched["final_url"],
            "content_type": fetched["content_type"],
            "error": fetched["error"],
            "tanseed_mentioned": bool(re.search(r"\btanseed\b", body_text, re.I)),
            "tanseed_specific_signals": signals,
            "deadline_signals": signals,
            "content_extraction": (
                "PDF bytes retrieved; PDF text not parsed by lightweight verifier"
                if fetched["reachable"] and "pdf" in fetched["content_type"].lower()
                else "HTML text extracted" if body_text else "No extractable HTML text"
            ),
        })
    reachable = sum(bool(x["reachable"]) for x in checked_sources)
    specific = sum(bool(x["tanseed_specific_signals"]) for x in checked_sources)
    summary = (
        f"{reachable}/{len(checked_sources)} configured sources reachable; "
        f"{specific} pages contained TANSEED-specific application signals. "
        "Neither reachability nor application wording proves a CURRENT open round. "
        "Confirm the latest dated call, deadline, and eligibility with StartupTN."
    )
    return {
        "checked_at": checked_at,
        "decision_type": "funding_application",
        "status": "UNKNOWN — MANUAL CONFIRMATION REQUIRED",
        "status_code": "UNKNOWN",
        "current_round_confirmed": False,
        "current_application_deadline": None,
        "eligibility_verified": False,
        "summary": summary,
        "sources_checked": checked_sources,
        "sources_reachable": reachable,
        "sources_total": len(checked_sources),
        "tanseed_mentioned_on_any_source": any(x["tanseed_mentioned"] for x in checked_sources),
        "deadline_or_application_signals_found": specific > 0,
        "historical_rounds": HISTORICAL_ROUNDS,
        "important_limit": "No automated OPEN/CLOSED determination. Historical calls, redirects, general Apply buttons, and network failures are not current scheme evidence.",
    }


def print_tanseed_verification(report: dict) -> None:
    print("\n" + "=" * 58)
    print("DECISIONROOM — OFFICIAL-SOURCE VERIFICATION")
    print("=" * 58)
    print("Checked at:", report["checked_at"])
    print("TANSEED application status:", report["status"])
    print("Sources reachable:", f"{report['sources_reachable']}/{report['sources_total']}")
    print("Conclusion:", report["summary"])
    for item in report["sources_checked"]:
        status = item["http_status"] if item["http_status"] is not None else "no response"
        print(f"\n- {item['name']}: HTTP {status}; reachable={item['reachable']}")
        print("  Requested:", item["url"])
        if item["final_url"] and item["final_url"] != item["url"]:
            print("  Final URL:", item["final_url"])
        if item["error"]:
            print("  Error:", item["error"])
        print("  Extraction:", item["content_extraction"])
        for signal in item["tanseed_specific_signals"][:2]:
            print("  TANSEED-specific text (not proof of open status):", signal)
    print("\nHistorical call context (not current availability):")
    for round_ in report["historical_rounds"]:
        print(f"- {round_['edition']}: announced deadline {round_['reported_deadline']}")
        print("  Source:", round_["source_url"])
    print("\nNote:", report["important_limit"])
