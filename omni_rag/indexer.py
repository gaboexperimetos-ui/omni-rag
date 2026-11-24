"""Construcción del índice: recorre fuentes, trocea y guarda JSON."""

from __future__ import annotations

import fnmatch
import json
import os
import time
from pathlib import Path
from typing import Callable

from .chunker import Chunk, chunk_note
from .config import DEFAULT_EXCLUDES, Config, Source, expand

INDEX_VERSION = 1


def file_key(source: str, path: str) -> str:
    return f"{source}:{path}"


def _is_excluded(relative: Path, source: Source) -> bool:
    patterns = list(DEFAULT_EXCLUDES) + list(source.exclude)
    parts = relative.parts
    for part in parts:
        if part.startswith("."):
            return True
        if part in DEFAULT_EXCLUDES or part in source.exclude:
            return True
    text = relative.as_posix()
    return any(fnmatch.fnmatch(text, pattern) for pattern in patterns if "*" in pattern)


def iter_files(source: Source) -> list[Path]:
    """Lista los archivos indexables de una fuente, en orden estable."""
    root = expand(source.path)
    if not root.exists():
        raise FileNotFoundError(f"la fuente '{source.name}' no existe: {root}")

    extensions = tuple(ext.lower() for ext in source.include_extensions)
    found: list[Path] = []
    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        dirs[:] = sorted(
            d for d in dirs
            if not _is_excluded(current_path.relative_to(root) / d, source)
        )
        for name in sorted(files):
            if name.startswith("."):
                continue
            if not name.lower().endswith(extensions):
                continue
            full = current_path / name
            if _is_excluded(full.relative_to(root), source):
                continue
            found.append(full)
    return found


def empty_index() -> dict:
    return {
        "version": INDEX_VERSION,
        "built_at": None,
        "sources": [],
        "files": {},
    }


def load_index(path: Path) -> dict:
    if not path.exists():
        return empty_index()
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (json.JSONDecodeError, OSError):
        return empty_index()
    if data.get("version") != INDEX_VERSION:
        return empty_index()
    data.setdefault("files", {})
    return data


def save_index(index: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(index, handle, ensure_ascii=False, separators=(",", ":"))
    os.replace(temporary, path)


def build(
    config: Config,
    *,
    force: bool = False,
    progress: Callable[[str], None] | None = None,
) -> dict:
    """Indexa todas las fuentes y devuelve el índice resultante.

    Los archivos sin cambios se reutilizan del índice anterior (mismo
    ``mtime_ns`` y tamaño), así que reindexar un vault grande es barato.
    """
    index_path = expand(config.index_path)
    previous = empty_index() if force else load_index(index_path)
    previous_files: dict = previous.get("files", {})

    files: dict[str, dict] = {}
    parsed = 0
    reused = 0
    skipped = 0
    errors: list[str] = []

    for source in config.sources:
        try:
            paths = iter_files(source)
        except FileNotFoundError as exc:
            errors.append(str(exc))
            if progress:
                progress(f"! {exc}")
            continue

        root = expand(source.path)
        for abs_path in paths:
            relative = abs_path.relative_to(root).as_posix()
            key = file_key(source.name, relative)
            try:
                stat = abs_path.stat()
            except OSError as exc:
                errors.append(f"{abs_path}: {exc}")
                continue

            old = previous_files.get(key)
            if (
                not force
                and old
                and old.get("mtime_ns") == stat.st_mtime_ns
                and old.get("size") == stat.st_size
            ):
                files[key] = old
                reused += 1
                continue

            try:
                text = abs_path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError) as exc:
                skipped += 1
                errors.append(f"{abs_path}: {exc}")
                continue

            chunks = chunk_note(source.name, relative, text)
            if not chunks:
                skipped += 1
                continue

            files[key] = {
                "source": source.name,
                "path": relative,
                "type": source.type,
                "mtime_ns": stat.st_mtime_ns,
                "size": stat.st_size,
                "chunks": [chunk.to_dict() for chunk in chunks],
            }
            parsed += 1
            if progress and parsed % 50 == 0:
                progress(f"  {parsed} archivos…")

    index = {
        "version": INDEX_VERSION,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "sources": [source.to_dict() for source in config.sources],
        "files": files,
        "stats": {
            "files": len(files),
            "chunks": sum(len(item["chunks"]) for item in files.values()),
            "parsed": parsed,
            "reused": reused,
            "skipped": skipped,
            "errors": errors[:20],
        },
    }
    save_index(index, index_path)
    return index


def all_chunks(index: dict) -> list[Chunk]:
    """Aplana el índice en una lista de fragmentos."""
    chunks: list[Chunk] = []
    for item in index.get("files", {}).values():
        for raw in item.get("chunks", []):
            chunks.append(Chunk.from_dict(raw))
    return chunks


def stats(index: dict) -> dict:
    chunks = all_chunks(index)
    lengths = sorted(len(chunk.text) for chunk in chunks)
    return {
        "sources": len(index.get("sources", [])),
        "files": len(index.get("files", {})),
        "chunks": len(chunks),
        "chars": sum(lengths),
        "median_chars": lengths[len(lengths) // 2] if lengths else 0,
        "max_chars": lengths[-1] if lengths else 0,
        "built_at": index.get("built_at"),
        "errors": index.get("stats", {}).get("errors", []),
    }
