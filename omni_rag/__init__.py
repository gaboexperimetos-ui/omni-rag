"""omni-rag: recuperación BM25 multi-fuente sobre notas Markdown."""

from __future__ import annotations

__version__ = "0.1.0"

from .chunker import Chunk, chunk_note
from .config import Config, Source, load, save
from .indexer import build, load_index, stats
from .search import Hit, context_block, format_hits, hits_to_json, query

__all__ = [
    "Chunk",
    "Config",
    "Hit",
    "Source",
    "build",
    "chunk_note",
    "context_block",
    "format_hits",
    "hits_to_json",
    "load",
    "load_index",
    "query",
    "save",
    "stats",
    "__version__",
]
