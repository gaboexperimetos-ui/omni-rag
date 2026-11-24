"""Catálogo de la biblioteca: notas, etiquetas, enlaces y salud del vault.

El índice de búsqueda guarda fragmentos; este módulo lo lee a nivel de nota y
resuelve los enlaces entre notas para responder preguntas de biblioteca:
qué está huérfano, qué enlace está roto, qué título está duplicado.
"""

from __future__ import annotations

import posixpath
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .config import Config, expand
from .indexer import load_index


@dataclass
class NoteInfo:
    key: str
    source: str
    path: str
    title: str
    tags: list[str]
    links: list[dict[str, Any]]
    chars: int
    words: int

    @property
    def reference(self) -> str:
        return f"[[{self.title}]]"

    @property
    def location(self) -> str:
        return f"{self.source}/{self.path}"


@dataclass
class Link:
    """Enlace resuelto desde una nota hacia otra (o hacia la nada)."""

    origin: str
    origin_title: str
    origin_path: str
    target: str
    line: int
    kind: str
    raw: str
    status: str
    resolved: list[str]

    @property
    def target_title(self) -> str:
        return self.resolved[0].split(":", 1)[-1] if self.resolved else self.target


def _note_from_item(key: str, item: dict[str, Any]) -> NoteInfo:
    meta = item.get("meta") or {}
    path = item.get("path", "")
    default_title = str(Path(path).stem)
    return NoteInfo(
        key=key,
        source=item.get("source", ""),
        path=path,
        title=str(meta.get("title") or default_title),
        tags=list(meta.get("tags") or []),
        links=list(meta.get("links") or []),
        chars=int(meta.get("chars") or 0),
        words=int(meta.get("words") or 0),
    )


class Catalog:
    """Vista de biblioteca sobre el índice ya construido."""

    def __init__(self, notes: dict[str, NoteInfo], groups: dict[str, list[str]] | None = None):
        self.notes = notes
        self.groups = dict(groups or {})
        self.names: dict[str, list[str]] = defaultdict(list)
        self.links: list[Link] = []
        self.incoming: dict[str, list[tuple[str, int]]] = defaultdict(list)
        self._index_names()
        self._resolve()

    # -- construcción -----------------------------------------------------

    def _index_names(self) -> None:
        for key, note in self.notes.items():
            for name in {
                note.title,
                Path(note.path).stem,
                posixpath.splitext(note.path)[0],
                posixpath.basename(note.path),
            }:
                normalized = name.casefold()
                if key not in self.names[normalized]:
                    self.names[normalized].append(key)

    def _candidates(self, target: str, kind: str) -> list[str]:
        key = target.casefold()
        found = list(self.names.get(key, []))
        if not found:
            base = posixpath.basename(target).casefold()
            found = list(self.names.get(base, []))
        return found

    def _resolve(self) -> None:
        for key, note in self.notes.items():
            for raw in note.links:
                target = str(raw.get("target", "")).strip()
                if not target:
                    continue
                candidates = self._candidates(target, str(raw.get("kind", "wiki")))
                if not candidates:
                    status = "broken"
                elif len(candidates) > 1:
                    status = "ambiguous"
                elif candidates[0] == key:
                    status = "self"
                else:
                    status = "ok"

                link = Link(
                    origin=key,
                    origin_title=note.title,
                    origin_path=note.path,
                    target=target,
                    line=int(raw.get("line", 0)),
                    kind=str(raw.get("kind", "wiki")),
                    raw=str(raw.get("raw", "")),
                    status=status,
                    resolved=candidates,
                )
                self.links.append(link)

                for destination in candidates:
                    if destination != key:
                        self.incoming[destination].append((key, link.line))

    # -- consultas --------------------------------------------------------

    def outgoing(self, key: str) -> list[Link]:
        return [link for link in self.links if link.origin == key]

    def backlinks(self, key: str) -> list[tuple[str, int]]:
        seen: list[tuple[str, int]] = []
        for origin, line in self.incoming.get(key, []):
            if not any(existing == origin for existing, _ in seen):
                seen.append((origin, line))
        return seen

    def broken(self) -> list[Link]:
        return [link for link in self.links if link.status == "broken"]

    def ambiguous(self) -> list[Link]:
        return [link for link in self.links if link.status == "ambiguous"]

    def orphans(self) -> list[NoteInfo]:
        """Notas sin enlaces entrantes ni salientes útiles."""
        result: list[NoteInfo] = []
        for key, note in self.notes.items():
            useful_out = [
                link
                for link in self.outgoing(key)
                if link.status in {"ok", "ambiguous"}
            ]
            if not useful_out and not self.backlinks(key):
                result.append(note)
        return sorted(result, key=lambda note: note.title.casefold())

    def tags(self) -> list[tuple[str, int]]:
        counter: Counter[str] = Counter()
        for note in self.notes.values():
            for tag in set(note.tags):
                counter[tag] += 1
        return counter.most_common()

    def collections(self) -> list[dict[str, Any]]:
        """Resumen por colección: fuentes y grupos.

        Un grupo (``colegio``) agrega varias fuentes sin reindexar nada.
        """
        groups: dict[str, list[NoteInfo]] = defaultdict(list)
        for note in self.notes.values():
            groups[note.source].append(note)

        result: list[dict[str, Any]] = []
        for name, notes in sorted(groups.items()):
            result.append(self._collection_row(name, notes, kind="fuente"))

        for name, members in sorted(self.groups.items()):
            notes = [
                note
                for member in members
                for note in groups.get(member, [])
            ]
            if notes:
                result.append(self._collection_row(name, notes, kind="grupo"))
        return result

    def _collection_row(
        self, name: str, notes: list[NoteInfo], *, kind: str
    ) -> dict[str, Any]:
        keys = {note.key for note in notes}
        tags = {tag for note in notes for tag in note.tags}
        links = [link for link in self.links if link.origin in keys]
        return {
            "name": name,
            "kind": kind,
            "notes": len(notes),
            "words": sum(note.words for note in notes),
            "chars": sum(note.chars for note in notes),
            "tags": len(tags),
            "links": len(links),
            "broken": sum(1 for link in links if link.status == "broken"),
            "orphans": sum(
                1
                for note in notes
                if not any(
                    link.status in {"ok", "ambiguous"}
                    for link in self.outgoing(note.key)
                )
                and not self.backlinks(note.key)
            ),
        }

    def duplicates(self) -> list[tuple[str, list[NoteInfo]]]:
        groups: dict[str, list[NoteInfo]] = defaultdict(list)
        for note in self.notes.values():
            groups[note.title.casefold()].append(note)
        return [
            (title, notes)
            for title, notes in sorted(groups.items())
            if len(notes) > 1
        ]

    def find(self, text: str) -> list[NoteInfo]:
        """Busca una nota por título o ruta: exacto, prefijo y subcadena."""
        wanted = text.casefold().strip()
        if not wanted:
            return []

        def score(note: NoteInfo) -> tuple[int, int]:
            title = note.title.casefold()
            path = note.path.casefold()
            if wanted == title or wanted == path or wanted == Path(path).stem:
                return (0, len(title))
            if title.startswith(wanted) or Path(path).stem.startswith(wanted):
                return (1, len(title))
            if wanted in title or wanted in path:
                return (2, len(title))
            return (9, len(title))

        matches = [note for note in self.notes.values() if score(note)[0] < 9]
        return sorted(matches, key=score)

    def summary(self) -> dict[str, Any]:
        tags = self.tags()
        return {
            "sources": len({note.source for note in self.notes.values()}),
            "notes": len(self.notes),
            "words": sum(note.words for note in self.notes.values()),
            "chars": sum(note.chars for note in self.notes.values()),
            "tags": len(tags),
            "links": len(self.links),
            "broken": len(self.broken()),
            "ambiguous": len(self.ambiguous()),
            "orphans": len(self.orphans()),
            "duplicates": len(self.duplicates()),
            "top_tags": tags[:10],
        }


def build(
    index: dict[str, Any] | None = None,
    config: Config | None = None,
    groups: dict[str, list[str]] | None = None,
) -> Catalog:
    """Construye el catálogo desde un índice o desde la config."""
    if index is None:
        if config is None:
            raise ValueError("hace falta un índice o una configuración")
        index = load_index(expand(config.index_path))
    if groups is None and config is not None:
        groups = config.groups
    notes = {
        key: _note_from_item(key, item)
        for key, item in index.get("files", {}).items()
    }
    return Catalog(notes, groups=groups)


def load(config: Config) -> Catalog:
    return build(config=config)
