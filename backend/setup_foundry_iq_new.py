"""
setup_foundry_iq.py
-------------------
One-time setup script to populate Azure AI Search with Buddy's behavioral framework.

Reads all markdown files from foundry_iq_docs/ and uploads them to the
'buddy-framework' index in Azure AI Search (Foundry IQ).

Index schema expected:
  id      (Edm.String, key)
  state   (Edm.String, searchable) — derived from filename
  content (Edm.String, searchable + retrievable) — full markdown content

Run once to populate, or re-run to update existing docs:
  python setup_foundry_iq.py
"""

import os
from pathlib import Path
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from dotenv import load_dotenv

load_dotenv()


def load_framework_docs() -> list:
    """
    Load all .md files from foundry_iq_docs/ and map them to index documents.
    The filename (without extension) becomes the 'state' field used for search.
    """
    docs_dir = Path(__file__).parent / "foundry_iq_docs"

    if not docs_dir.exists():
        print(f"❌ Directory not found: {docs_dir}")
        return []

    documents = []
    for doc_id, md_file in enumerate(sorted(docs_dir.glob("*.md")), start=1):
        content = md_file.read_text(encoding="utf-8")
        documents.append({
            "id":      str(doc_id),
            "state":   md_file.stem,
            "content": content,
        })

    return documents


def setup_foundry_iq():
    """Upload all framework docs to Azure AI Search."""
    endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
    key      = os.getenv("AZURE_SEARCH_KEY")

    if not endpoint or not key or key == "<get-from-azure-portal-keys>":
        print("❌ Azure credentials not configured in .env")
        print("Set AZURE_SEARCH_ENDPOINT and AZURE_SEARCH_KEY first.")
        return

    documents = load_framework_docs()

    if not documents:
        print("❌ No framework documents found in foundry_iq_docs/")
        return

    try:
        search_client = SearchClient(
            endpoint=endpoint,
            index_name="buddy-framework",
            credential=AzureKeyCredential(key),
        )

        print(f"📚 Uploading {len(documents)} framework documents from markdown files...")
        result = search_client.upload_documents(documents=documents)

        print(f"✅ Successfully uploaded {len(result)} documents:")
        for doc in documents:
            print(f"   - {doc['state']}")

        print("\n🎯 Foundry IQ is ready! Your docs are now searchable.")

    except Exception as e:
        print(f"❌ Error: {e}")
        print("Note: The index 'buddy-framework' must exist in Azure Portal first.")
        print("See: https://learn.microsoft.com/en-us/azure/search/search-get-started-portal")


if __name__ == "__main__":
    setup_foundry_iq()
