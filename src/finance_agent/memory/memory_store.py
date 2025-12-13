"""
Persistent memory store using ChromaDB.

- Stores important user preferences and finance insights as embeddings
- Persists to disk so memory survives restarts
"""

from pathlib import Path
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings


class MemoryStore:
    def __init__(self, persist_dir: str = "memory/chroma"):
        # Ensure the folder exists (creates memory/chroma on disk)
        Path(persist_dir).mkdir(parents=True, exist_ok=True)

        # Embedding model used to convert text -> vectors
        embeddings = OpenAIEmbeddings()

        # Persistent vector store (writes files under memory/chroma)
        self.vectordb = Chroma(
            collection_name="finance_agent_memory",
            embedding_function=embeddings,
            persist_directory=persist_dir,
        )

    def add(self, text: str, metadata: dict | None = None):
        """
        Add a memory item (text) to Chroma with optional metadata.
        """
        metadata = metadata or {}
        self.vectordb.add_texts([text], metadatas=[metadata])

    def search(self, query: str, k: int = 5):
        """
        Retrieve the top-k most relevant memories.
        """
        results = self.vectordb.similarity_search(query, k=k)
        return [{"text": r.page_content, "metadata": r.metadata} for r in results]
