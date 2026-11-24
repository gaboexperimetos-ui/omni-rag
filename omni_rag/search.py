"""Búsqueda, formato de resultados y bloques de contexto para LLM."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable

from . import backends
from .chunker import Chunk
from .config import Config, expand
from .tokenize import normalize_phrase, tokenize


@dataclass
class Hit:
    score: float
    chunk: Chunk
    kind: str = "obsidian"


def _kinds(index: dict) -> dict[tuple[str, str], str]:
    kinds: dict[tuple[str, str], str] = {}
    for item in index.get("files", {}).values():
        kinds[(item.get("source", ""), item.get("path", ""))] = item.get("type", "dir")
    return kinds


def searcher(config: Config):
    """Crea el backend configurado cargando el índice desde disco."""
    from .indexer import load_index

    index = load_index(expand(config.index_path))
    return backends.create(
        config.backend,
        index,
        k1=config.k1,
        b=config.b,
    )


def query(
    config: Config,
    text: str,
    *,
    k: int = 5,
    source: str | None = None,
    tag: str | None = None,
    path: str | None = None,
) -> list[Hit]:
    """Busca ``text`` y aplica filtros de fuente, etiqueta o ruta."""
    from .indexer import load_index

    index = load_index(expand(config.index_path))
    retriever = backends.create(
        config.backend,
        index,
        k1=config.k1,
        b=config.b,
    )
    filters_active = bool(source or tag or path)
    candidates = retriever.search(text, k=k * 10 if filters_active else k)

    kinds = _kinds(index)
    phrase = normalize_phrase(text)
    terms = set(tokenize(text))
    hits: list[Hit] = []

    for score, chunk in candidates:
        if source and chunk.source != source:
            continue
        if path and path.lower() not in chunk.path.lower():
            continue
        if tag:
            wanted = tag.lower().lstrip("#")
            if wanted not in {item.lower() for item in chunk.tags}:
                continue

        if phrase and len(terms) > 1:
            body = normalize_phrase(f"{chunk.heading} {chunk.text}")
            if phrase and phrase in body:
                score *= 1.15

        hits.append(
            Hit(
                score=score,
                chunk=chunk,
                kind=kinds.get((chunk.source, chunk.path), "dir"),
            )
        )

    hits.sort(key=lambda hit: hit.score, reverse=True)
    return hits[:k]


def reference(hit: Hit) -> str:
    if hit.kind == "obsidian":
        return f"[[{hit.chunk.note}]]"
    return f"{hit.chunk.source}/{hit.chunk.path}"


def location(hit: Hit) -> str:
    chunk = hit.chunk
    where = f"{chunk.source}/{chunk.path}:{chunk.line}"
    if chunk.heading and chunk.heading != chunk.note:
        where += f" · {chunk.heading}"
    return where


def snippet(chunk: Chunk, text: str, limit: int = 240) -> str:
    """Frase con más coincidencias de la consulta, recortada a ``limit``."""
    terms = set(tokenize(text))
    sentences = [
        part.strip()
        for part in chunk.text.replace("\n", " ").split(". ")
        if part.strip()
    ]
    if not sentences:
        sentences = [" ".join(chunk.text.split())]

    best = sentences[0]
    best_hits = -1
    for sentence in sentences:
        found = len(terms & set(tokenize(sentence)))
        if found > best_hits:
            best, best_hits = sentence, found

    clean = " ".join(best.split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "…"


def format_hits(hits: Iterable[Hit], text: str, *, numbered: bool = True) -> str:
    lines: list[str] = []
    for position, hit in enumerate(hits, start=1):
        prefix = f"{position}) " if numbered else "- "
        lines.append(f"{prefix}{reference(hit)}  ({hit.score:.3f})")
        lines.append(f"   {location(hit)}")
        lines.append(f"   {snippet(hit.chunk, text)}")
    return "\n".join(lines)


def context_block(
    hits: Iterable[Hit],
    *,
    max_tokens: int = 4000,
    max_chars_per_chunk: int = 1200,
) -> str:
    """Bloque de contexto recortado a un presupuesto aproximado de tokens.

    Se usa la heurística de ~4 caracteres por token, suficiente para decidir
    cuánto pegar en un prompt.
    """
    budget = max_tokens * 4
    parts: list[str] = []
    used = 0

    for position, hit in enumerate(hits, start=1):
        chunk = hit.chunk
        body = chunk.text.strip()
        if len(body) > max_chars_per_chunk:
            body = body[: max_chars_per_chunk - 1].rstrip() + "…"

        header = (
            f"[{position}] {reference(hit)} — {chunk.source}/{chunk.path}:{chunk.line}"
        )
        if chunk.heading and chunk.heading != chunk.note:
            header += f" — {chunk.heading}"

        block = f"{header}\n{body}"
        if used + len(block) > budget:
            remaining = budget - used
            if remaining < 200:
                break
            block = block[: remaining - 1].rstrip() + "…"
        parts.append(block)
        used += len(block) + 2
        if used >= budget:
            break

    return "\n\n---\n\n".join(parts)


def hits_to_json(hits: Iterable[Hit], text: str) -> str:
    payload = [
        {
            "score": round(hit.score, 6),
            "source": hit.chunk.source,
            "path": hit.chunk.path,
            "line": hit.chunk.line,
            "note": hit.chunk.note,
            "heading": hit.chunk.heading,
            "tags": hit.chunk.tags,
            "reference": reference(hit),
            "snippet": snippet(hit.chunk, text),
            "text": hit.chunk.text,
        }
        for hit in hits
    ]
    return json.dumps(payload, ensure_ascii=False, indent=2)
