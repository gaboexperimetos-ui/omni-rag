"""Backends de recuperación enchufables.

Hoy solo existe ``bm25`` (léxico, sin modelos). El registro existe para que un
backend futuro — embeddings, API remota, MCP — se añada sin tocar el CLI:

    from .backends import register, Retriever

    @register("embeddings")
    class EmbeddingsRetriever:
        name = "embeddings"
        def __init__(self, index, config): ...
        def search(self, query, k): ...
"""

from __future__ import annotations

from typing import Callable, Protocol, Sequence

from .bm25 import BM25
from .chunker import Chunk
from .indexer import all_chunks


class Retriever(Protocol):
    name: str

    def search(self, query: str, k: int) -> list[tuple[float, Chunk]]:
        """Devuelve (puntuación, fragmento) ordenados de mayor a menor."""


_REGISTRY: dict[str, Callable[..., Retriever]] = {}


def register(name: str) -> Callable[[Callable[..., Retriever]], Callable[..., Retriever]]:
    def decorator(factory: Callable[..., Retriever]) -> Callable[..., Retriever]:
        _REGISTRY[name] = factory
        return factory

    return decorator


def available() -> list[str]:
    return sorted(_REGISTRY)


def create(name: str, index: dict, **options) -> Retriever:
    if name not in _REGISTRY:
        raise ValueError(
            f"backend desconocido: {name!r} (disponibles: {', '.join(available())})"
        )
    return _REGISTRY[name](index, **options)


@register("bm25")
class Bm25Retriever:
    """Recuperación léxica BM25 sobre los fragmentos del índice."""

    name = "bm25"

    def __init__(self, index: dict, k1: float = 1.5, b: float = 0.75):
        from .tokenize import tokenize

        self.chunks = all_chunks(index)
        self._tokenize = tokenize
        documents: list[Sequence[str]] = [
            self._weighted(chunk) for chunk in self.chunks
        ]
        self.bm25 = BM25(documents, k1=k1, b=b)

    def _weighted(self, chunk: Chunk) -> list[str]:
        from .bm25 import weighted_tokens

        return weighted_tokens(
            chunk.text,
            title=chunk.note,
            heading=chunk.heading,
            tags=chunk.tags,
        )

    def search(self, query: str, k: int = 5) -> list[tuple[float, Chunk]]:
        terms = self._tokenize(query)
        if not terms or not self.chunks:
            return []
        scores = self.bm25.scores(terms)
        ranked = sorted(
            zip(scores, self.chunks),
            key=lambda item: item[0],
            reverse=True,
        )
        return [(score, chunk) for score, chunk in ranked[: max(1, k)] if score > 0]
