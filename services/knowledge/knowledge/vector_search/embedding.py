import hashlib
import math
import os
import re

TOKEN_RE = re.compile(r"[a-z0-9]+")


class EmbeddingModel:
    """Interface every embedding backend implements."""

    dim: int

    def embed(self, text: str) -> list[float]:
        raise NotImplementedError


class HashingEmbedding(EmbeddingModel):
    """
    Fully local, deterministic, zero external downloads — chosen
    specifically because this environment cannot reach HuggingFace Hub
    (confirmed: 403 Forbidden) to fetch real transformer embedding
    weights, and has no route to a live Ollama instance either.

    This is a legitimate technique (feature hashing / "the hashing
    trick"), not a placeholder — every vector is real, and search
    against it is exact cosine-similarity retrieval. It captures
    LEXICAL overlap, not true semantic similarity: it has no notion
    that "car" and "automobile" are related, unlike a real transformer
    embedding. Meaningfully weaker for paraphrase-heavy queries — see
    OllamaEmbedding below for the intended production path.
    """

    def __init__(self, dim: int = 512):
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        tokens = TOKEN_RE.findall((text or "").lower())
        for token in tokens:
            h = int(hashlib.sha256(token.encode()).hexdigest(), 16)
            vec[h % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec


class OllamaEmbedding(EmbeddingModel):
    """
    Calls Ollama's real embedding API (POST /api/embeddings). Written to
    Ollama's documented request/response contract, but NOT live-tested
    against a real Ollama instance — this sandbox has no network route
    to one. Verify against your actual Ollama deployment before relying
    on this; HashingEmbedding above is what's actually been exercised
    end to end in this build.
    """

    def __init__(self, model: str = "nomic-embed-text", base_url: str = None, dim: int = 768):
        self.model = model
        self.base_url = base_url or os.environ.get("OLLAMA_URL", "http://localhost:11434")
        self.dim = dim  # matches nomic-embed-text; adjust if you point this at a different model

    def embed(self, text: str) -> list[float]:
        import httpx

        resp = httpx.post(
            f"{self.base_url}/api/embeddings", json={"model": self.model, "prompt": text}, timeout=30.0
        )
        resp.raise_for_status()
        return resp.json()["embedding"]


def get_default_embedding_model() -> EmbeddingModel:
    backend = os.environ.get("EMBEDDING_BACKEND", "hashing")
    if backend == "ollama":
        return OllamaEmbedding()
    return HashingEmbedding()
