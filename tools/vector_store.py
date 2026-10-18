"""Vector store abstraction and Qdrant implementation for DecisionRoom.

Provides:
- Persistent local Qdrant storage (or remote when configured)
- Strict multi-tenant company/project metadata isolation
- Document re-indexing, duplicate detection, and deletion
- Source-grounded EvidenceCitation extraction
- Configurable real embedding model abstraction

Embedding providers:
- HuggingFaceEmbedder: real semantic embeddings via sentence-transformers
  Default model: nomic-ai/nomic-embed-text-v1.5, dimension=768
- FastHashEmbedder: deterministic, dependency-free lexical projection.
  Allowed ONLY as an explicitly-labelled fallback or in unit tests.
  Must NOT be the silent production default.

Dimension mismatch protection: checks existing collection config and raises
instead of silently destroying data or writing incompatible vectors.
"""
from __future__ import annotations

import hashlib
import logging
import math
import re
import threading
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from config.config import settings
from schemas.decision import EvidenceCitation
from tools.document_parser import DocumentChunk

logger = logging.getLogger("decisionroom.vector_store")

COLLECTION_NAME = "company_documents"
# shortcut: dimension is fixed per embedding model. Change requires versioned collection + re-index.
EMBEDDING_DIM_HASH = 384   # FastHashEmbedder (test/fallback only)
EMBEDDING_DIM_HF = 768     # HuggingFaceEmbedder nomic-embed-text-v1.5


def _stable_hash(s: str) -> int:
    """Deterministic integer hash independent of Python process hash seeds."""
    return int(hashlib.md5(s.encode("utf-8")).hexdigest()[:8], 16)


class BaseEmbedder(ABC):
    """Abstract interface for embedding generation."""
    dimension: int

    @abstractmethod
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        pass

    def embed_query(self, query: str) -> List[float]:
        return self.embed_texts([query])[0]

    def label(self) -> str:
        """Human-readable embedder label for logging and config status."""
        return self.__class__.__name__


class FastHashEmbedder(BaseEmbedder):
    """Deterministic, dependency-free lexical dense embedder.

    For UNIT TESTS and explicitly-labelled degraded fallback ONLY.
    Must not be used as the silent production default.
    It does NOT produce semantic embeddings.
    """
    dimension: int = EMBEDDING_DIM_HASH

    def __init__(self, dimension: int = EMBEDDING_DIM_HASH):
        self.dimension = dimension

    def _embed_single(self, text: str) -> List[float]:
        vec = np.zeros(self.dimension, dtype=np.float32)
        words = re.findall(r"\w+", text.lower())
        if not words:
            return vec.tolist()
        for word in words:
            h = _stable_hash(word) % self.dimension
            vec[h] += 1.0
            if len(word) >= 3:
                for i in range(len(word) - 2):
                    tg_h = _stable_hash(word[i : i + 3]) % self.dimension
                    vec[tg_h] += 0.3
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return [self._embed_single(t) for t in texts]

    def label(self) -> str:
        return f"FastHashEmbedder(dim={self.dimension}) [DEGRADED-LEXICAL]"


class HuggingFaceEmbedder(BaseEmbedder):
    """Real semantic embedder via sentence-transformers.

    Default: nomic-ai/nomic-embed-text-v1.5, dimension=768 (normalized).
    Validates output dimension against configured value before returning.
    """

    def __init__(
        self,
        model_name: str = "nomic-ai/nomic-embed-text-v1.5",
        expected_dim: int = EMBEDDING_DIM_HF,
        trust_remote_code: bool = True,
    ):
        self.model_name = model_name
        self.dimension = expected_dim
        self._trust_remote_code = trust_remote_code
        self._model: Any = None

    def _get_model(self) -> Any:
        if self._model is None:
            try:
                import torch
                import transformers
                if not hasattr(transformers.PreTrainedModel, "get_extended_attention_mask"):
                    def _compat_get_extended_attention_mask(self_m, attention_mask, input_shape, dtype=None):
                        if dtype is None:
                            dtype = self_m.dtype
                        if attention_mask.dim() == 3:
                            extended_attention_mask = attention_mask[:, None, :, :]
                        elif attention_mask.dim() == 2:
                            extended_attention_mask = attention_mask[:, None, None, :]
                        else:
                            raise ValueError(f"Wrong shape for attention_mask (shape {attention_mask.shape})")
                        return (1.0 - extended_attention_mask) * torch.finfo(dtype).min

                    transformers.PreTrainedModel.get_extended_attention_mask = _compat_get_extended_attention_mask

                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(
                    self.model_name,
                    trust_remote_code=self._trust_remote_code,
                )
            except ImportError as exc:
                raise RuntimeError(
                    "sentence-transformers is required for HuggingFaceEmbedder. "
                    "Run: pip install sentence-transformers"
                ) from exc
        return self._model

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        model = self._get_model()
        # nomic-embed models require a task prefix for asymmetric retrieval
        prefixed = [f"search_document: {t}" for t in texts]
        vecs = model.encode(prefixed, normalize_embeddings=True)
        result = []
        for v in vecs:
            arr = np.asarray(v, dtype=np.float32)
            if arr.shape[0] != self.dimension:
                raise ValueError(
                    f"HuggingFaceEmbedder produced dim={arr.shape[0]}, "
                    f"expected {self.dimension}. Mismatch for model {self.model_name}."
                )
            result.append(arr.tolist())
        return result

    def embed_query(self, query: str) -> List[float]:
        model = self._get_model()
        # Use search_query prefix for query-side
        prefixed = f"search_query: {query}"
        vec = model.encode(prefixed, normalize_embeddings=True)
        arr = np.asarray(vec, dtype=np.float32)
        if arr.shape[0] != self.dimension:
            raise ValueError(
                f"HuggingFaceEmbedder query produced dim={arr.shape[0]}, expected {self.dimension}."
            )
        return arr.tolist()

    def label(self) -> str:
        return f"HuggingFaceEmbedder({self.model_name}, dim={self.dimension})"


# Embedder instances are expensive (HF model load) — cache per provider key so
# repeated QdrantVectorStore() construction in API endpoints doesn't reload the model.
_EMBEDDER_CACHE: Dict[str, BaseEmbedder] = {}


def build_embedder(
    force_hash: bool = False,
) -> BaseEmbedder:
    """Build the configured embedder (cached per provider; force_hash bypasses the cache).

    Args:
        force_hash: If True, always return FastHashEmbedder (test injection).

    Returns:
        HuggingFaceEmbedder when embedding_provider=='huggingface' (default),
        FastHashEmbedder only when explicitly requested or provider is 'hash'.
    """
    if force_hash:
        return FastHashEmbedder()

    provider = settings.embedding_provider.lower()
    if provider == "hash":
        # Explicit opt-in to degraded lexical fallback; log clearly
        logger.warning(
            "EMBEDDING_PROVIDER=hash selected. Using FastHashEmbedder (DEGRADED-LEXICAL). "
            "This is NOT semantic search. Set EMBEDDING_PROVIDER=huggingface for production."
        )
        return FastHashEmbedder()

    # Default: huggingface
    cached = _EMBEDDER_CACHE.get(provider)
    if cached is None:
        cached = HuggingFaceEmbedder(
            model_name=settings.embedding_model_name,
            expected_dim=settings.embedding_dimension,
        )
        _EMBEDDER_CACHE[provider] = cached
    return cached


# Shared production store: local-mode Qdrant locks its storage path, so a second
# concurrent instance would fail to open the same directory. Cache the no-arg instance.
_default_store: Optional["QdrantVectorStore"] = None
_default_store_lock = threading.Lock()


def get_vector_store() -> "QdrantVectorStore":
    """Return the shared production QdrantVectorStore (thread-safe singleton)."""
    global _default_store
    if _default_store is None:
        with _default_store_lock:
            if _default_store is None:
                _default_store = QdrantVectorStore()
    return _default_store


class QdrantVectorStore:
    """Production vector store using Qdrant with tenant-isolated filtering.

    Dimension mismatch protection:
    - Reads existing collection config before creating.
    - Raises if existing collection has a different vector size.
    - Does NOT silently destroy existing data.
    - Use a versioned collection name or run re-indexing when model changes.
    """

    def __init__(
        self,
        embedder: Optional[BaseEmbedder] = None,
        in_memory: bool = False,
        collection_name: Optional[str] = None,
        _force_hash_embedder: bool = False,
    ):
        # _force_hash_embedder or in_memory: for tests only; production uses build_embedder()
        if embedder is not None:
            self.embedder = embedder
        elif _force_hash_embedder or in_memory:
            self.embedder = FastHashEmbedder()
        else:
            self.embedder = build_embedder()

        if collection_name is not None:
            self.collection_name = collection_name
        else:
            # Versioned collection: preserve legacy 384 collection and avoid dimension collision
            self.collection_name = (
                COLLECTION_NAME if self.embedder.dimension == EMBEDDING_DIM_HASH
                else f"{COLLECTION_NAME}_v{self.embedder.dimension}"
            )
        self.in_memory = in_memory

        from qdrant_client import QdrantClient
        from qdrant_client.http import models

        self.models = models

        if in_memory:
            self.client = QdrantClient(":memory:")
        elif settings.is_qdrant_configured:
            self.client = QdrantClient(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key,
                timeout=settings.request_timeout_seconds,
            )
        else:
            settings.qdrant_local_path.mkdir(parents=True, exist_ok=True)
            self.client = QdrantClient(path=str(settings.qdrant_local_path))

        self._ensure_collection()

    def _ensure_collection(self) -> None:
        """Create or validate Qdrant collection. Raises on dimension mismatch to protect existing data."""
        expected_dim = self.embedder.dimension
        existing = {c.name: c for c in self.client.get_collections().collections}

        if self.collection_name in existing:
            # Verify the existing collection uses a compatible vector size
            try:
                info = self.client.get_collection(self.collection_name)
                existing_dim = info.config.params.vectors.size
                if existing_dim != expected_dim:
                    raise ValueError(
                        f"Collection '{self.collection_name}' has vector size={existing_dim}, "
                        f"but current embedder ({self.embedder.label()}) produces dim={expected_dim}. "
                        f"Dimension mismatch: cannot mix embedding models in the same collection. "
                        f"Use a versioned collection name or re-index with EMBEDDING_DIMENSION={existing_dim}."
                    )
            except Exception as exc:
                if "Dimension mismatch" in str(exc):
                    raise
                logger.warning("Could not verify collection dimension: %s", exc)
            return

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=self.models.VectorParams(
                size=expected_dim,
                distance=self.models.Distance.COSINE,
            ),
        )
        logger.info(
            "Created Qdrant collection '%s' with dim=%d embedder=%s",
            self.collection_name, expected_dim, self.embedder.label(),
        )
        # Create payload indices for remote Qdrant or if explicitly running persistent mode
        if not self.in_memory:
            for field in ("company_id", "project_id", "doc_hash"):
                try:
                    self.client.create_payload_index(
                        collection_name=self.collection_name,
                        field_name=field,
                        field_schema=self.models.PayloadSchemaType.KEYWORD,
                    )
                except Exception as exc:
                    logger.debug("Payload index '%s' creation skipped: %s", field, exc)

    def index_chunks(self, chunks: List[DocumentChunk]) -> int:
        """Index chunks with payload metadata and tenant scopes."""
        if not chunks:
            return 0

        texts = [c.text for c in chunks]
        embeddings = self.embedder.embed_texts(texts)

        points = []
        for chunk, emb in zip(chunks, embeddings):
            if len(emb) != self.embedder.dimension:
                raise ValueError(
                    f"Embedding dimension mismatch: got {len(emb)}, expected {self.embedder.dimension}"
                )
            # Scope the point ID by tenant: chunk_id alone (doc-hash based) would collide
            # when the same file content is uploaded under two companies or projects,
            # and the later upload would silently overwrite the earlier scope's vectors.
            point_id = _stable_hash(f"{chunk.company_id}|{chunk.project_id}|{chunk.chunk_id}") % (2**63 - 1)
            points.append(
                self.models.PointStruct(
                    id=point_id,
                    vector=emb,
                    payload=chunk.to_dict(),
                )
            )

        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
        )
        return len(points)

    def search(
        self,
        query: str,
        company_id: str,
        project_id: Optional[str] = None,
        top_k: int = 5,
        min_score: float = 0.20,
    ) -> List[EvidenceCitation]:
        """Search with mandatory company isolation filter. project_id='default' does NOT widen scope."""
        query_vec = self.embedder.embed_query(query)

        must_conditions: list[Any] = [
            self.models.FieldCondition(
                key="company_id",
                match=self.models.MatchValue(value=company_id),
            )
        ]
        if project_id and project_id != "default":
            # Only filter by project when explicitly scoped — "default" means per-company-wide
            must_conditions.append(
                self.models.FieldCondition(
                    key="project_id",
                    match=self.models.MatchValue(value=project_id),
                )
            )

        search_filter = self.models.Filter(must=must_conditions)

        query_response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vec,
            query_filter=search_filter,
            limit=top_k * 2,
            score_threshold=min_score,
        )
        results = query_response.points

        citations: List[EvidenceCitation] = []
        seen_texts: set[str] = set()

        for hit in results:
            payload = hit.payload or {}
            snippet = str(payload.get("text", "")).strip()
            norm = " ".join(snippet.lower().split()[:20])

            if norm in seen_texts:
                continue
            seen_texts.add(norm)

            citations.append(
                EvidenceCitation(
                    source_id=str(payload.get("chunk_id", hit.id)),
                    title=str(payload.get("document_name", "Company Document")),
                    document=str(payload.get("document_name", "")),
                    page_or_section=str(payload.get("page_or_section", "General")),
                    snippet=snippet,
                    # shortcut: verified=False; no independent verification step exists
                    verified=False,
                )
            )
            if len(citations) >= top_k:
                break

        return citations

    def delete_document(
        self,
        company_id: str,
        doc_hash: str,
        project_id: Optional[str] = None,
    ) -> bool:
        """Delete chunks for a document by hash, scoped to company (+ project when given).

        Returns True if the delete executed (Qdrant by-filter deletes don't report counts)."""
        must_conditions: list[Any] = [
            self.models.FieldCondition(
                key="company_id",
                match=self.models.MatchValue(value=company_id),
            ),
            self.models.FieldCondition(
                key="doc_hash",
                match=self.models.MatchValue(value=doc_hash),
            ),
        ]
        if project_id:
            # Same file content may legitimately live in several projects; without this
            # filter a project-scoped delete would also destroy sibling projects' vectors.
            must_conditions.append(
                self.models.FieldCondition(
                    key="project_id",
                    match=self.models.MatchValue(value=project_id),
                )
            )
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=self.models.FilterSelector(
                    filter=self.models.Filter(must=must_conditions)
                ),
            )
            return True
        except Exception as exc:
            logger.error("delete_document failed for hash=%s company=%s: %s", doc_hash, company_id, exc)
            return False

    def delete_by_document(self, document_name: str, company_id: str) -> None:
        """Delete all chunks for a named document belonging to a company."""
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=self.models.FilterSelector(
                filter=self.models.Filter(
                    must=[
                        self.models.FieldCondition(
                            key="company_id",
                            match=self.models.MatchValue(value=company_id),
                        ),
                        self.models.FieldCondition(
                            key="document_name",
                            match=self.models.MatchValue(value=document_name),
                        ),
                    ]
                )
            ),
        )

    def delete_by_hash(self, doc_hash: str, company_id: str) -> None:
        """Delete document points matching content hash (alias for delete_document)."""
        self.delete_document(company_id=company_id, doc_hash=doc_hash)
