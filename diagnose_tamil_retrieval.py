from pathlib import Path
import json
import faiss
from sentence_transformers import SentenceTransformer

root = Path(".")
index = faiss.read_index(str(root / "vector_db/government_policy.index"))
metadata = json.loads(
    (root / "vector_db/government_policy_metadata.json").read_text(encoding="utf-8")
)
model = SentenceTransformer("all-MiniLM-L6-v2")

query = (
    "Tamil Nadu Startup and Innovation Policy 2023 TANSEED funding "
    "eligibility seed investment and government procurement concessions"
)
embedding = model.encode(
    [query], normalize_embeddings=True, convert_to_numpy=True
).astype("float32")

scores, indices = index.search(embedding, min(403, index.ntotal))

print("\nTOP TAMIL NADU MATCHES:")
shown = 0

for score, idx in zip(scores[0], indices[0]):
    item = metadata[idx]
    source = item.get("document", "")
    if "Tamil_Nadu" in source:
        print(
            f"\nScore: {float(score):.4f}"
            f"\nSource: {source}"
            f"\nChunk: {item.get('chunk_number')}"
            f"\nText: {item.get('text', '')[:500]}"
        )
        shown += 1
        if shown >= 10:
            break

print("\nTamil Nadu matches displayed:", shown)
