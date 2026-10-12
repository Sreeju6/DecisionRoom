import os
import json
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer


# ==============================
# CONFIGURATION
# ==============================

INPUT_FILE = "data/processed/rag_documents.json"

VECTOR_DB_FOLDER = "vector_db"

INDEX_FILE = os.path.join(
    VECTOR_DB_FOLDER,
    "government_policy.index"
)

METADATA_FILE = os.path.join(
    VECTOR_DB_FOLDER,
    "government_policy_metadata.json"
)

MODEL_NAME = "all-MiniLM-L6-v2"


# ==============================
# LOAD DOCUMENT CHUNKS
# ==============================

def load_chunks():

    print("\n========== LOADING DOCUMENT CHUNKS ==========")

    with open(
        INPUT_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        chunks = json.load(file)

    print("Chunks loaded:", len(chunks))

    return chunks


# ==============================
# LOAD EMBEDDING MODEL
# ==============================

def load_embedding_model():

    print("\n========== LOADING EMBEDDING MODEL ==========")

    print(f"Model: {MODEL_NAME}")

    model = SentenceTransformer(MODEL_NAME)

    print("Embedding model loaded successfully.")

    return model


# ==============================
# CREATE EMBEDDINGS
# ==============================

def create_embeddings(model, chunks):

    print("\n========== CREATING EMBEDDINGS ==========")

    texts = [
        chunk["text"]
        for chunk in chunks
    ]

    embeddings = model.encode(
        texts,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True
    )

    print("Embedding shape:", embeddings.shape)

    return embeddings


# ==============================
# BUILD FAISS INDEX
# ==============================

def build_faiss_index(embeddings):

    print("\n========== BUILDING FAISS INDEX ==========")

    dimension = embeddings.shape[1]

    print("Embedding dimension:", dimension)

    # Inner Product works as cosine similarity
    # because embeddings are normalized.
    index = faiss.IndexFlatIP(dimension)

    index.add(
        embeddings.astype(np.float32)
    )

    print("Vectors added:", index.ntotal)

    return index


# ==============================
# SAVE DATABASE
# ==============================

def save_database(index, chunks):

    print("\n========== SAVING VECTOR DATABASE ==========")

    os.makedirs(
        VECTOR_DB_FOLDER,
        exist_ok=True
    )

    faiss.write_index(
        index,
        INDEX_FILE
    )

    with open(
        METADATA_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            chunks,
            file,
            ensure_ascii=False,
            indent=2
        )

    print("FAISS index saved to:")
    print(INDEX_FILE)

    print("\nMetadata saved to:")
    print(METADATA_FILE)


# ==============================
# MAIN
# ==============================

def main():

    print("\n========================================")
    print("   DECISIONROOM VECTOR DATABASE")
    print("========================================")

    chunks = load_chunks()

    model = load_embedding_model()

    embeddings = create_embeddings(
        model,
        chunks
    )

    index = build_faiss_index(
        embeddings
    )

    save_database(
        index,
        chunks
    )

    print("\n========== SUCCESS ==========")

    print(
        f"Vector database created with "
        f"{index.ntotal} document chunks."
    )


if __name__ == "__main__":
    main()