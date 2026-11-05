"""
Ingest Buddy's behavioral framework documents into Qdrant.
Run once (or whenever buddy_docs/ changes) to populate the vector DB.

Setup before running:
1. Create a free cluster at https://cloud.qdrant.io
2. Get your cluster URL and API key
3. Set them as environment variables:
   QDRANT_URL=https://xxxx.cloud.qdrant.io
   QDRANT_API_KEY=your-key-here
"""

import os
import glob
import frontmatter
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer

QDRANT_URL = os.environ.get("QDRANT_URL")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY")
COLLECTION_NAME = "buddy_framework"
DOCS_DIR = os.path.join(os.path.dirname(__file__), "buddy_docs")

EMBED_MODEL_NAME = "BAAI/bge-small-en-v1.5"


def load_documents():
    docs = []
    for path in glob.glob(os.path.join(DOCS_DIR, "*.md")):
        post = frontmatter.load(path)
        docs.append({
            "doc_id": post.get("doc_id", os.path.basename(path)),
            "category": post.get("category", "unknown"),
            "state": post.get("state"),
            "intervention": post.get("intervention"),
            "designed_for_states": post.get("designed_for_states", []),
            "content": post.content,
            "filename": os.path.basename(path)
        })
    return docs


def main():
    if not QDRANT_URL or not QDRANT_API_KEY:
        raise RuntimeError(
            "Set QDRANT_URL and QDRANT_API_KEY environment variables first. "
            "Get a free cluster at https://cloud.qdrant.io"
        )

    print("Loading embedding model (bge-small-en-v1.5)...")
    model = SentenceTransformer(EMBED_MODEL_NAME)

    print("Loading documents...")
    docs = load_documents()
    print(f"Found {len(docs)} documents")

    print("Connecting to Qdrant...")
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    if client.collection_exists(COLLECTION_NAME):
        client.delete_collection(COLLECTION_NAME)
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=384, distance=Distance.COSINE)
    )
    print(f"Created collection '{COLLECTION_NAME}'")

    texts_to_embed = [f"passage: {d['content']}" for d in docs]

    print("Generating embeddings...")
    embeddings = model.encode(texts_to_embed, show_progress_bar=True)

    points = [
        PointStruct(
            id=i,
            vector=embeddings[i].tolist(),
            payload={
                "doc_id": docs[i]["doc_id"],
                "category": docs[i]["category"],
                "state": docs[i]["state"],
                "intervention": docs[i]["intervention"],
                "designed_for_states": docs[i]["designed_for_states"],
                "content": docs[i]["content"],
                "filename": docs[i]["filename"]
            }
        )
        for i in range(len(docs))
    ]

    print("Uploading to Qdrant...")
    client.upsert(collection_name=COLLECTION_NAME, points=points)
    print(f"✅ Ingested {len(points)} documents into Qdrant collection '{COLLECTION_NAME}'")


if __name__ == "__main__":
    main()