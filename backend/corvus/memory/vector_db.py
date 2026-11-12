"""ChromaDB vector store for Corvus local semantic search."""

from pathlib import Path


class ChromaManager:
    def __init__(self, path: Path, collection_name: str = "documents"):
        # Imported here: chromadb is slow to import and only needed once an
        # embedding model is available.
        import chromadb
        from chromadb.config import Settings

        path.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=str(path), settings=Settings(anonymized_telemetry=False)
        )
        self.collection = self.client.get_or_create_collection(
            name=collection_name, metadata={"hnsw:space": "cosine"}
        )

    def add_documents(
        self,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict] | None = None,
    ) -> None:
        if documents:
            self.collection.upsert(
                ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas
            )

    def delete_path(self, path: str) -> None:
        self.collection.delete(where={"path": path})

    def query(self, query_embeddings: list[list[float]], n_results: int = 5) -> dict:
        return self.collection.query(query_embeddings=query_embeddings, n_results=n_results)

    def count(self) -> int:
        return self.collection.count()
