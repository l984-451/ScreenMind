"""
Embedding Engine
Generates semantic embeddings for activity summaries using
sentence-transformers. Used for natural language search over activities.
"""

import numpy as np
from typing import List, Optional


class Embedder:
    """
    Generates 384-dimensional embeddings using all-MiniLM-L6-v2.
    Tiny (80MB), runs on CPU instantly, doesn't compete for GPU with Gemma.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self._model_name = model_name
        self._model = None
        self._initialized = False

    def _ensure_model(self):
        """Lazy-load the embedding model on first use."""
        if not self._initialized:
            try:
                from sentence_transformers import SentenceTransformer

                print(f"[Embedder] Loading model: {self._model_name}...")
                self._model = SentenceTransformer(self._model_name)
                self._initialized = True
                print(f"[Embedder] Model loaded. Dimensions: {self._model.get_sentence_embedding_dimension()}")
            except ImportError:
                print("[Embedder] sentence-transformers not installed. Semantic search disabled.")
                raise
            except Exception as e:
                print(f"[Embedder] Failed to load model: {e}")
                raise

    def embed_text(self, text: str) -> List[float]:
        """
        Generate an embedding vector for a text string.

        Args:
            text: The text to embed (typically activity summary + details).

        Returns:
            List of 384 floats representing the semantic embedding.
        """
        self._ensure_model()
        embedding = self._model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    def embed_activity(
        self,
        summary: str = "",
        details: str = "",
        visible_text: Optional[List[str]] = None,
        app_name: str = "",
        category: str = "",
        scene_description: str = "",
    ) -> List[float]:
        """
        Generate an embedding for an activity by combining multiple text fields.
        This produces better search results than embedding just the summary.

        Args:
            summary: Activity summary from Gemma.
            details: Detailed context from Gemma.
            visible_text: Text snippets visible on screen.
            app_name: Application name.
            category: Activity category.
            scene_description: Rich visual narration of the screenshot.

        Returns:
            384-dimensional embedding vector.
        """
        # Combine fields with decreasing importance
        parts = []
        if summary:
            parts.append(summary)
        if scene_description:
            # Truncate for embedding (MiniLM has 256 token limit)
            parts.append(scene_description[:500])
        if details:
            parts.append(details)
        if app_name:
            parts.append(f"Application: {app_name}")
        if category:
            parts.append(f"Category: {category}")
        if visible_text:
            parts.append("Visible: " + " | ".join(visible_text[:5]))

        combined = ". ".join(parts)
        return self.embed_text(combined)

    def search(
        self,
        query: str,
        embeddings: List[List[float]],
        top_k: int = 10,
    ) -> List[tuple]:
        """
        Find the most similar embeddings to a query.

        Args:
            query: Natural language search query.
            embeddings: List of stored embedding vectors.
            top_k: Number of top results to return.

        Returns:
            List of (index, similarity_score) tuples, sorted by relevance.
        """
        self._ensure_model()

        if not embeddings:
            return []

        query_embedding = np.array(self.embed_text(query))
        stored = np.array(embeddings)

        # Cosine similarity (embeddings are already normalized)
        similarities = stored @ query_embedding

        # Get top-k indices
        top_indices = np.argsort(similarities)[::-1][:top_k]

        return [
            (int(idx), float(similarities[idx]))
            for idx in top_indices
            if similarities[idx] > 0.1  # Min relevance threshold
        ]

    @property
    def dimensions(self) -> int:
        """Embedding dimensions (384 for all-MiniLM-L6-v2)."""
        return 384

    @property
    def is_available(self) -> bool:
        """Check if the embedding model can be loaded."""
        try:
            self._ensure_model()
            return True
        except Exception:
            return False
