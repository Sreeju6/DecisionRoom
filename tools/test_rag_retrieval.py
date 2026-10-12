
import json
import re
import faiss
from sentence_transformers import SentenceTransformer


INDEX_FILE = "vector_db/government_policy.index"
METADATA_FILE = "vector_db/government_policy_metadata.json"
MODEL_NAME = "all-MiniLM-L6-v2"

STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar",
    "Chhattisgarh", "Goa", "Gujarat", "Haryana",
    "Himachal Pradesh", "Jammu and Kashmir", "Jharkhand",
    "Karnataka", "Kerala", "Ladakh", "Madhya Pradesh",
    "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha",
    "Puducherry", "Punjab", "Rajasthan", "Sikkim",
    "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh",
    "Uttarakhand", "West Bengal"
]

STOPWORDS = {
    "what", "which", "are", "is", "the", "for", "in",
    "of", "a", "an", "to", "and", "available", "does",
    "do", "can", "startup", "startups", "support"
}

NAVIGATION_TERMS = [
    "contents", "table of contents", "annexure",
    "chapter", "policy pillars", "page number"
]


def load_rag():
    print("\n========== LOADING RAG DATABASE ==========")

    index = faiss.read_index(INDEX_FILE)

    with open(METADATA_FILE, "r", encoding="utf-8") as file:
        metadata = json.load(file)

    model = SentenceTransformer(MODEL_NAME)

    print(f"FAISS vectors: {index.ntotal}")
    print(f"Metadata chunks: {len(metadata)}")

    if index.ntotal != len(metadata):
        raise ValueError(
            "FAISS vector count and metadata count do not match."
        )

    return index, metadata, model


def detect_state(query):
    query_lower = query.lower()

    for state in sorted(STATES, key=len, reverse=True):
        pattern = r"\b" + re.escape(state.lower()) + r"\b"

        if re.search(pattern, query_lower):
            return state

    return None


def get_document_state(document_name):
    filename = document_name.lower().replace("_", " ")

    for state in sorted(STATES, key=len, reverse=True):
        if state.lower() in filename:
            return state

    return None


def query_keywords(query):
    words = re.findall(r"[a-zA-Z]+", query.lower())

    return {
        word for word in words
        if word not in STOPWORDS and len(word) > 2
    }


def calculate_relevance(query, text):
    keywords = query_keywords(query)
    text_lower = text.lower()

    if not keywords:
        return 0.0

    matched = sum(
        1 for word in keywords
        if re.search(r"\b" + re.escape(word) + r"\b", text_lower)
    )

    return matched / len(keywords)


def is_navigation_heavy(text):
    text_lower = text.lower()

    matches = sum(
        1 for term in NAVIGATION_TERMS
        if term in text_lower
    )

    return matches >= 3


def search(query, index, metadata, model, top_k=5):
    query_embedding = model.encode(
        [query],
        convert_to_numpy=True,
        normalize_embeddings=True
    )

    candidate_k = min(50, index.ntotal)

    scores, indices = index.search(
        query_embedding.astype("float32"),
        candidate_k
    )

    detected_state = detect_state(query)
    candidates = []

    for score, index_position in zip(scores[0], indices[0]):
        if index_position == -1:
            continue

        result = metadata[index_position].copy()
        text = result.get("text", "")
        document_state = get_document_state(result["document"])

        similarity = float(score)
        relevance = calculate_relevance(query, text)
        state_match = (
            detected_state is not None
            and document_state == detected_state
        )

        # Transparent combined ranking score.
        rerank_score = (
            0.65 * similarity
            + 0.25 * relevance
            + (0.10 if state_match else 0.0)
        )

        if is_navigation_heavy(text):
            rerank_score -= 0.08

        result["document_state"] = document_state
        result["similarity_score"] = similarity
        result["keyword_relevance"] = relevance
        result["state_match"] = state_match
        result["rerank_score"] = rerank_score

        candidates.append(result)

    candidates.sort(
        key=lambda item: item["rerank_score"],
        reverse=True
    )

    return detected_state, candidates[:top_k]


def display_results(query, detected_state, results):
    print("\n========================================")
    print("QUERY")
    print("========================================")
    print(query)
    print(f"\nDetected State: {detected_state or 'None'}")

    print("\n========== RETRIEVED EVIDENCE ==========")

    for number, result in enumerate(results, start=1):
        print("\n----------------------------------------")
        print(f"Result {number}")
        print("----------------------------------------")
        print(f"Document: {result['document']}")
        print(f"State: {result['document_state']}")
        print(f"Chunk: {result['chunk_number']}")
        print(f"Similarity: {result['similarity_score']:.4f}")
        print(f"Keyword relevance: {result['keyword_relevance']:.4f}")
        print(f"Rerank score: {result['rerank_score']:.4f}")
        print(f"State match: {result['state_match']}")
        print("\nText:")
        print(result["text"])


def main():
    index, metadata, model = load_rag()

    queries = [
        "What startup incentives are available in Tamil Nadu?",
        "What startup support is available in Karnataka?",
        "What financial support is available for startups?"
    ]

    for query in queries:
        detected_state, results = search(
            query, index, metadata, model, top_k=5
        )

        display_results(query, detected_state, results)


if __name__ == "__main__":
    main()
