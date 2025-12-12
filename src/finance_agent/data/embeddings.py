import chromadb
from chromadb.utils import embedding_functions


class MemoryStore:
    """
    Very simple semantic memory using Chroma.

    It stores past conversation snippets as text and lets us
    retrieve similar ones based on a new query.
    """

    def __init__(self):
        # Create an in-memory Chroma client
        self.chroma = chromadb.Client()

        # Default embedding function (Chroma’s built-in)
        self.embedder = embedding_functions.DefaultEmbeddingFunction()

        # Collection = like a table for our memory
        self.collection = self.chroma.get_or_create_collection(
            name="finance_memory",
            embedding_function=self.embedder,
        )

    def add(self, user: str, assistant: str) -> None:
        """
        Store a user ↔ assistant exchange in memory.
        """
        text = f"User: {user}\nAssistant: {assistant}"
        new_id = f"id_{self.collection.count()}"
        self.collection.add(
            documents=[text],
            ids=[new_id],
        )

    def search(self, query: str, top_k: int = 3) -> list[str]:
        """
        Return up to top_k similar memory snippets for the given query.
        """
        if self.collection.count() == 0:
            return []

        results = self.collection.query(
            query_texts=[query],
            n_results=top_k,
        )

        # results["documents"] is a list-of-lists
        return results["documents"][0] if results["documents"] else []
