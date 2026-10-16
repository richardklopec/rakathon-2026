"""Text embeddings. Default: local multilingual ONNX model via fastembed (Czech works, ~0.2 GB, CPU).

The model is downloaded once into backend/var/models. Document text never leaves the machine.
"""

from functools import lru_cache

from app.config import get_settings


@lru_cache
def _local_model():
    from fastembed import TextEmbedding  # heavy import, load lazily

    s = get_settings()
    return TextEmbedding(s.local_embedding_model, cache_dir=str(s.data_dir / "models"))


def embed(texts: list[str]) -> list[list[float]]:
    s = get_settings()
    if s.embedding_backend == "gateway":
        from app import llm

        return llm.embed(texts)
    return [v.tolist() for v in _local_model().embed(texts, batch_size=64)]
