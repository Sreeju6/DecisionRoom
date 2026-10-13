"""Unit tests for QdrantVectorStore and tenant isolation."""
import pytest

from tools.document_parser import DocumentChunk
from tools.vector_store import QdrantVectorStore, FastHashEmbedder


def create_mock_chunks(company_id: str, doc_name: str, texts: list[str]) -> list[DocumentChunk]:
    return [
        DocumentChunk(
            chunk_id=f"{company_id}_{doc_name}_{i}",
            company_id=company_id,
            project_id="proj_1",
            document_name=doc_name,
            doc_hash=f"hash_{company_id}_{doc_name}",
            page_or_section=f"Section {i}",
            text=text,
        )
        for i, text in enumerate(texts)
    ]


def test_qdrant_indexing_and_search():
    store = QdrantVectorStore(in_memory=True, collection_name="test_collection")
    chunks = create_mock_chunks("acme_corp", "pricing.txt", [
        "Acme enterprise annual subscription price is $50,000.",
        "Acme small business tier is $1,200 per year.",
    ])
    indexed_count = store.index_chunks(chunks)
    assert indexed_count == 2

    # Query for subscription price
    results = store.search(query="subscription price", company_id="acme_corp", top_k=2)
    assert len(results) >= 1
    assert "Acme" in results[0].snippet
    assert results[0].title == "pricing.txt"


def test_qdrant_strict_tenant_isolation():
    store = QdrantVectorStore(in_memory=True, collection_name="test_isolation")

    # Index confidential document for Company A
    store.index_chunks(create_mock_chunks("company_a", "secret_strategy.txt", [
        "Confidential Project Pegasus acquisition target is Delta Ltd for $15M."
    ]))

    # Index document for Company B
    store.index_chunks(create_mock_chunks("company_b", "public_plan.txt", [
        "Company B quarterly hiring plans for 10 software engineers."
    ]))

    # Company B searches for Pegasus / acquisition -> MUST RETURN 0 RESULTS
    results_b = store.search(query="Project Pegasus acquisition Delta", company_id="company_b")
    assert len(results_b) == 0

    # Company A searches -> receives citation
    results_a = store.search(query="Project Pegasus acquisition", company_id="company_a")
    assert len(results_a) == 1
    assert "Delta Ltd" in results_a[0].snippet


def test_qdrant_document_deletion():
    store = QdrantVectorStore(in_memory=True, collection_name="test_deletion")
    chunks = create_mock_chunks("acme", "temp.txt", ["Temporary policy content."])
    store.index_chunks(chunks)

    res_before = store.search(query="policy content", company_id="acme")
    assert len(res_before) == 1

    # Delete by document name
    store.delete_by_document("temp.txt", company_id="acme")
    res_after = store.search(query="policy content", company_id="acme")
    assert len(res_after) == 0


def test_qdrant_no_hit_insufficient_evidence():
    store = QdrantVectorStore(in_memory=True, collection_name="test_nohit")
    # Search empty vector store
    results = store.search(query="unrelated query about astrophysics", company_id="acme")
    assert results == []
