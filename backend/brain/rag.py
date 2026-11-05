"""
rag.py
------
Replaces Foundry IQ (Azure AI Search) with a free, self-hosted-friendly stack:
  - Qdrant Cloud (free tier) for vector storage
  - bge-small-en-v1.5 (local, free) for embeddings

This is a drop-in replacement for query_foundry_iq() in agent.py.
Same input/output shape, so the rest of agent.py doesn't need to change —
only the import and the function call site.
"""

import os
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
COLLECTION_NAME = "buddy_framework"
EMBED_MODEL_NAME = "BAAI/bge-small-en-v1.5"

# Lazy singletons — model loads once per process, not once per request
_model = None
_client = None


def _get_model():
    global _model
    if _model is None:
        print("Loading embedding model (bge-small-en-v1.5)...")
        _model = SentenceTransformer(EMBED_MODEL_NAME)
    return _model


def _get_client():
    global _client
    if _client is None:
        if not QDRANT_URL or not QDRANT_API_KEY:
            raise RuntimeError(
                "QDRANT_URL and QDRANT_API_KEY must be set. "
                "Get a free cluster at https://cloud.qdrant.io"
            )
        _client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, check_compatibility=False)
    return _client


def query_buddy_framework(query: str, top_k: int = 3) -> str:
    """
    Drop-in replacement for query_foundry_iq().
    Same signature: takes a query string, returns a joined text blob of
    relevant framework content — agent.py's decide_intervention() consumes
    this exactly the same way it consumed the Azure Search result.
    """
    try:
        model = _get_model()
        client = _get_client()

        query_vector = model.encode(f"query: {query}").tolist()
        results = client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            limit=top_k
        ).points

        if not results:
            return _fallback(query)

        docs = [r.payload["content"] for r in results]
        return "\n\n".join(docs)

    except Exception as e:
        print(f"Qdrant retrieval error: {e}. Falling back to LLM.")
        return _fallback(query)


def _fallback(query: str) -> str:
    """
    Fallback if Qdrant is unreachable (network issue, not configured yet, etc).
    Mirrors agent.py's existing _fallback_foundry_iq pattern so behavior
    degrades gracefully instead of crashing the whole agent loop.
    """
    from groq import Groq
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are Buddy's knowledge base. You have deep expertise in accountability "
                    "frameworks and intervention psychology. Answer questions about Buddy's behavioral "
                    "philosophy, do/don't rules, and recommended interventions for different work states."
                ),
            },
            {"role": "user", "content": query},
        ],
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


def query_buddy_framework_structured(state: str, top_k_interventions: int = 3) -> dict:
    """
    Richer retrieval for when you want state definition + interventions separately
    instead of one merged text blob. Optional upgrade for later — not required
    for the drop-in swap.
    """
    model = _get_model()
    client = _get_client()
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    state_vector = model.encode(f"query: state definition and characteristics of {state}").tolist()
    state_results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=state_vector,
        limit=1,
        query_filter=Filter(must=[FieldCondition(key="category", match=MatchValue(value="state_definition"))])
    ).points

    interv_vector = model.encode(f"query: intervention technique designed for someone experiencing {state}").tolist()
    interv_results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=interv_vector,
        limit=top_k_interventions,
        query_filter=Filter(must=[FieldCondition(key="category", match=MatchValue(value="intervention"))])
    ).points

    return {
        "state_definition": state_results[0].payload["content"] if state_results else None,
        "candidate_interventions": [
            {"doc_id": r.payload["doc_id"], "content": r.payload["content"], "score": r.score}
            for r in interv_results
        ]
    }