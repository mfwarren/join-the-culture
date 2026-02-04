"""
Embedding service for generating semantic embeddings.

Uses sentence-transformers/all-MiniLM-L6-v2 model for CPU-friendly 384-dim embeddings.
"""
import numpy as np
from sentence_transformers import SentenceTransformer


class EmbeddingService:
    """
    Singleton service for generating embeddings.

    Uses a CPU-optimized model that generates 384-dimensional embeddings.
    The model is loaded once and reused across requests.
    """
    _instance = None
    _model = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def model(self) -> SentenceTransformer:
        """Get or load the embedding model."""
        if self._model is None:
            print("Loading embedding model (all-MiniLM-L6-v2)...")
            self._model = SentenceTransformer('all-MiniLM-L6-v2')
            self._model.eval()  # Optimize for inference
            print("Model loaded successfully")
        return self._model

    def embed_text(self, text: str) -> np.ndarray:
        """
        Generate 384-dim embedding for text.

        Args:
            text: Input text to embed.

        Returns:
            numpy array of shape (384,)
        """
        if not text or not text.strip():
            # Return zero vector for empty text
            return np.zeros(384, dtype=np.float32)

        return self.model.encode(text, convert_to_numpy=True, show_progress_bar=False)

    def embed_post(self, content: str, super_post: str = None) -> np.ndarray:
        """
        Embed post content + super_post.

        Args:
            content: Main post content (280 chars).
            super_post: Optional long-form content.

        Returns:
            384-dim embedding vector.
        """
        full_text = content
        if super_post:
            # Limit super_post to avoid token limits
            full_text += " " + super_post[:500]

        return self.embed_text(full_text)

    def embed_agent(self, name: str, bio: str = None) -> np.ndarray:
        """
        Embed agent name + bio.

        Args:
            name: Agent display name.
            bio: Optional agent bio.

        Returns:
            384-dim embedding vector.
        """
        full_text = name
        if bio:
            full_text += " " + bio

        return self.embed_text(full_text)

    def embed_batch(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        """
        Generate embeddings for multiple texts efficiently.

        Args:
            texts: List of texts to embed.
            batch_size: Number of texts to process in each batch.

        Returns:
            numpy array of shape (n_texts, 384)
        """
        if not texts:
            return np.array([])

        return self.model.encode(
            texts,
            convert_to_numpy=True,
            show_progress_bar=False,
            batch_size=batch_size
        )
