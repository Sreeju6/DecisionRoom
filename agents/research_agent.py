import json
import os
from pathlib import Path

import faiss
from sentence_transformers import SentenceTransformer


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

# Resolve paths relative to the project root, not the terminal's
# current working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = PROJECT_ROOT / "vector_db" / "government_policy.index"
METADATA_PATH = PROJECT_ROOT / "vector_db" / "government_policy_metadata.json"

MODEL_NAME = "all-MiniLM-L6-v2"

# Search more candidates before filtering to the target state.
DEFAULT_TOP_K = 5
MAX_CANDIDATES = 403
MIN_SIMILARITY = 0.20

_model = None
_index = None
_metadata = None


# --------------------------------------------------
# LOAD RAG RESOURCES
# --------------------------------------------------

def load_research_resources():
    """Load the embedding model, FAISS index, and metadata."""
    global _model, _index, _metadata

    if _model is not None and _index is not None and _metadata is not None:
        return

    if not INDEX_PATH.is_file():
        raise FileNotFoundError(
            f"FAISS index not found: {INDEX_PATH}\n"
            "Run: python tools\\build_vector_db.py"
        )

    if not METADATA_PATH.is_file():
        raise FileNotFoundError(
            f"Metadata file not found: {METADATA_PATH}"
        )

    print("Loading embedding model...")
    _model = SentenceTransformer(MODEL_NAME)

    print("Loading FAISS index...")
    _index = faiss.read_index(str(INDEX_PATH))

    with METADATA_PATH.open("r", encoding="utf-8") as file:
        _metadata = json.load(file)

    if _index.ntotal != len(_metadata):
        raise ValueError(
            f"Index contains {_index.ntotal} vectors, but metadata "
            f"contains {len(_metadata)} records."
        )

    print(f"Research resources loaded: {len(_metadata)} chunks")


# --------------------------------------------------
# STATE DETECTION
# --------------------------------------------------

STATES = [
    "Andhra Pradesh",
    "Arunachal Pradesh",
    "Himachal Pradesh",
    "Jammu and Kashmir",
    "Madhya Pradesh",
    "Tamil Nadu",
    "Uttar Pradesh",
    "West Bengal",
    "Karnataka",
    "Maharashtra",
    "Telangana",
    "Rajasthan",
    "Gujarat",
    "Haryana",
    "Kerala",
    "Punjab",
    "Chhattisgarh",
    "Jharkhand",
    "Uttarakhand",
    "Puducherry",
    "Meghalaya",
    "Nagaland",
    "Mizoram",
    "Manipur",
    "Tripura",
    "Sikkim",
    "Assam",
    "Bihar",
    "Goa",
    "Odisha",
    "Ladakh",
    "Delhi",
]


def detect_state(query):
    """Return the state explicitly mentioned in a query, if any."""
    query_lower = query.casefold()

    for state in sorted(STATES, key=len, reverse=True):
        if state.casefold() in query_lower:
            return state

    return None


def get_document_state(filename):
    """Extract a state name from a policy filename."""
    name = Path(str(filename)).name

    
    for suffix in (
        "_startup_and_innovation_policy_2023.txt",
        "_startup_policy_evidence.txt",
        "_startup_policy.txt",
    ):

        if name.casefold().endswith(suffix.casefold()):
            name = name[:-len(suffix)]
            break

    return name.replace("_", " ").strip()


def _metadata_state(item):
    """Use explicit metadata state when available, otherwise infer from filename."""
    explicit_state = item.get("state") or item.get("state_ut")
    if isinstance(explicit_state, str) and explicit_state.strip():
        return explicit_state.strip()
    return get_document_state(item.get("document", "Unknown source"))


def _normalise_text(text):
    """Create a lightweight comparison string for duplicate detection."""
    return " ".join(str(text).casefold().split())


def _add_caution(result):
    """Attach a caution when evidence signals historical policy information."""
    evidence_lower = result["evidence"].casefold()

    historical_signals = (
        "historical unless verified",
        "must not merge historical benefits",
        "historical",
    )
    current_policy_signals = (
        "current policy",
        "current benefits",
        "current-policy",
    )

    if any(signal in evidence_lower for signal in historical_signals) and (
        any(signal in evidence_lower for signal in current_policy_signals)
        or "historical" in evidence_lower
    ):
        result["caution"] = (
            "This evidence mentions historical policy details. Verify the "
            "current policy and scheme guidelines before presenting those "
            "details as currently available benefits."
        )

    return result


# --------------------------------------------------
# RETRIEVE POLICY EVIDENCE
# --------------------------------------------------

def search_policy_evidence(query, top_k=DEFAULT_TOP_K):
    """
    Retrieve policy evidence relevant to a research question.

    If a state is specified, results from other states are excluded.
    Results are ranked by FAISS similarity and near-duplicate text is
    skipped. The function returns evidence, not a final recommendation.
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Enter a non-empty research question.")

    if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
        raise ValueError("top_k must be a positive integer.")

    load_research_resources()
    target_state = detect_state(query)

    query_embedding = _model.encode(
        [query.strip()],
        convert_to_numpy=True,
        normalize_embeddings=True,
    ).astype("float32")

    candidate_count = min(MAX_CANDIDATES, _index.ntotal)
    scores, indices = _index.search(query_embedding, candidate_count)

    results = []
    seen_text = set()

    for score, idx in zip(scores[0], indices[0]):
        if idx < 0 or idx >= len(_metadata):
            continue

        similarity = float(score)
        if similarity < MIN_SIMILARITY:
            continue

        item = _metadata[idx]
        evidence = str(item.get("text", "")).strip()
        if not evidence:
            continue

        document_state = _metadata_state(item)

        # Never silently mix other states into a state-specific search.
        if target_state and document_state.casefold() != target_state.casefold():
            continue

        normalised = _normalise_text(evidence)
        if normalised in seen_text:
            continue
        seen_text.add(normalised)

        result = {
            "source": item.get("document", "Unknown source"),
            "state": document_state,
            "chunk_number": item.get("chunk_number"),
            "similarity": round(similarity, 4),
            "evidence": evidence,
        }
        results.append(_add_caution(result))

        if len(results) >= top_k:
            break

    return {
        "query": query,
        "target_state": target_state,
        "result_count": len(results),
        "results": results,
        "candidates_searched": candidate_count,
        "similarity_threshold": MIN_SIMILARITY,
    }


# --------------------------------------------------
# DISPLAY RESULTS
# --------------------------------------------------

def print_research_results(report):
    """Print retrieved evidence and caveats."""
    print("\n" + "=" * 55)
    print("DECISIONROOM — RESEARCH AGENT")
    print("=" * 55)

    print(f"Question: {report['query']}")
    print(f"Target state: {report['target_state'] or 'Not specified'}")
    print(f"Evidence records retrieved: {report['result_count']}")

    if "candidates_searched" in report:
        print(f"Candidates searched: {report['candidates_searched']}")
        print(f"Minimum similarity: {report['similarity_threshold']}")

    if not report["results"]:
        print(
            "\nNo matching evidence was found in the current index. "
            "This does not prove that no policy evidence exists; the "
            "source documents may be missing or retrieval may not match "
            "the wording of the question."
        )
        return

    for number, result in enumerate(report["results"], start=1):
        print("\n" + "-" * 55)
        print(f"EVIDENCE {number}")
        print("-" * 55)
        print(f"State: {result['state']}")
        print(f"Source file: {result['source']}")
        print(f"Chunk: {result['chunk_number']}")
        print(f"Similarity: {result['similarity']}")
        print("\nRetrieved text:")
        print(result["evidence"])

        if result.get("caution"):
            print("\nIMPORTANT CAUTION:")
            print(result["caution"])

    print("\n" + "=" * 55)
    print("These are retrieved sources, not a final recommendation.")
    print("Check policy dates, eligibility, and source reliability.")
    print("=" * 55)


# --------------------------------------------------
# RUN INTERACTIVELY
# --------------------------------------------------

if __name__ == "__main__":
    print("\nDecisionRoom Research Agent")
    print("Ask a question about startup policies.")
    print("Type 'exit' to quit.")

    while True:
        try:
            question = input("\nEnter your research question: ").strip()

            if question.casefold() in {"exit", "quit"}:
                print("Research Agent closed.")
                break

            if not question:
                print("Please enter a question.")
                continue

            report = search_policy_evidence(question, top_k=5)
            print_research_results(report)

        except KeyboardInterrupt:
            print("\nResearch Agent closed.")
            break

        except Exception as error:
            print(f"\nERROR: {error}")
