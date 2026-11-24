"""Troceado de notas Markdown/Obsidian en fragmentos buscables."""

from __future__ import annotations

import os
import posixpath
import re
from dataclasses import dataclass, field, asdict
from typing import Any
from urllib.parse import unquote

from .tokenize import inline_tags

FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?", re.S)
HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$", re.M)
WIKILINK_RE = re.compile(r"(!?)\[\[([^\]|#]*)(?:#([^\]|]*))?(?:\|([^\]]*))?\]\]")
MDLINK_RE = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")

MAX_CHARS = 900
MIN_CHARS = 140
OVERLAP_CHARS = 180


@dataclass
class Chunk:
    """Fragmento de una nota, con la ruta de encabezados que lo contiene."""

    source: str
    path: str
    line: int
    heading: str
    text: str
    note: str
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Chunk":
        return cls(
            source=data["source"],
            path=data["path"],
            line=int(data["line"]),
            heading=data.get("heading", ""),
            text=data["text"],
            note=data.get("note", ""),
            tags=list(data.get("tags", [])),
        )


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str, int]:
    """Separa el frontmatter YAML del cuerpo.

    Solo entiende el subconjunto que usa Obsidian en este vault: escalares,
    listas entre corchetes y listas en bloque con guiones.

    Devuelve (metadatos, cuerpo, líneas consumidas por el frontmatter).
    """
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text, 0

    meta: dict[str, Any] = {}
    current_key: str | None = None
    for raw in match.group(1).splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.lstrip().startswith("- ") and current_key:
            meta.setdefault(current_key, [])
            if isinstance(meta[current_key], list):
                meta[current_key].append(_scalar(line.lstrip()[2:]))
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        current_key = key
        if not value:
            meta[key] = []
        elif value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            meta[key] = [_scalar(v) for v in inner.split(",")] if inner else []
        else:
            meta[key] = _scalar(value)

    consumed = text[: match.end()].count("\n")
    return meta, text[match.end():], consumed


def _scalar(value: str) -> str:
    value = value.strip().strip('"').strip("'")
    return value.strip()


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [v.strip() for v in value.split(",") if v.strip()]
    return []


def _shorten(text: str, limit: int = 110) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _split_long(text: str, start_line: int, max_chars: int, overlap: int) -> list[tuple[str, int]]:
    """Parte un texto largo por párrafos, con solape entre trozos."""
    paragraphs = [p for p in re.split(r"\n[ \t]*\n", text) if p.strip()]
    if not paragraphs:
        return []

    pieces: list[tuple[str, int]] = []
    buffer: list[str] = []
    buffer_line = start_line
    cursor_line = start_line

    def flush() -> None:
        if buffer:
            pieces.append(("\n\n".join(buffer), buffer_line))

    for paragraph in paragraphs:
        para_lines = paragraph.count("\n") + 1
        candidate_len = len("\n\n".join(buffer)) + (2 if buffer else 0) + len(paragraph)

        if buffer and candidate_len > max_chars:
            flush()
            carry: list[str] = []
            carry_len = 0
            carry_line = cursor_line
            for previous in reversed(buffer):
                if carry_len + len(previous) > overlap:
                    break
                carry.insert(0, previous)
                carry_len += len(previous) + 2
                carry_line -= previous.count("\n") + 1
            buffer = carry
            buffer_line = max(start_line, carry_line)

        if len(paragraph) > max_chars:
            # Párrafo gigantesco (tabla, bloque de código): corte duro.
            flush()
            offset = 0
            while offset < len(paragraph):
                end = min(offset + max_chars, len(paragraph))
                if end < len(paragraph):
                    space = paragraph.rfind("\n", offset + max_chars // 2, end)
                    if space > offset:
                        end = space
                piece = paragraph[offset:end]
                if piece.strip():
                    line = start_line + paragraph[:offset].count("\n")
                    pieces.append((piece, line))
                if end >= len(paragraph):
                    break
                offset = max(end - overlap // 2, offset + 1)
            buffer = []
            cursor_line = start_line + para_lines
            continue

        buffer.append(paragraph)
        cursor_line += para_lines

    flush()
    return pieces


@dataclass
class Note:
    """Nota completa: metadatos, enlaces y fragmentos buscables."""

    source: str
    path: str
    title: str
    tags: list[str]
    links: list[dict[str, Any]]
    chunks: list[Chunk]
    chars: int
    words: int

    def to_meta(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "tags": list(self.tags),
            "links": list(self.links),
            "chars": self.chars,
            "words": self.words,
        }


def normalize_target(raw: str) -> str:
    """Normaliza el destino de un enlace para compararlo con rutas y títulos."""
    value = raw.strip().replace("\\", "/")
    if value.lower().endswith(".md"):
        value = value[:-3]
    return value.strip()


def _local_target(raw: str, note_path: str) -> str | None:
    """Resuelve un enlace Markdown relativo; None si es externo o ancla."""
    if SCHEME_RE.match(raw):
        return None
    target = unquote(raw.split("#", 1)[0].strip())
    if not target:
        return None
    if target.startswith("/"):
        joined = target.lstrip("/")
    else:
        joined = posixpath.join(posixpath.dirname(note_path), target)
    joined = posixpath.normpath(joined)
    if joined.startswith(".."):
        return None
    return normalize_target(joined)


def extract_links(body: str, start_line: int, note_path: str) -> list[dict[str, Any]]:
    """Extrae wikilinks y enlaces Markdown locales, con su línea."""
    links: list[dict[str, Any]] = []
    in_fence = False

    for offset, line in enumerate(body.splitlines()):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        number = start_line + offset
        for match in WIKILINK_RE.finditer(line):
            embed, target, heading, alias = match.groups()
            target = normalize_target(target)
            if not target:
                continue
            links.append(
                {
                    "kind": "wiki",
                    "target": target,
                    "heading": (heading or "").strip() or None,
                    "alias": (alias or "").strip() or None,
                    "embed": bool(embed),
                    "line": number,
                    "raw": match.group(0),
                }
            )

        for match in MDLINK_RE.finditer(line):
            label, raw_target = match.groups()
            target = _local_target(raw_target, note_path)
            if not target:
                continue
            links.append(
                {
                    "kind": "md",
                    "target": target,
                    "heading": None,
                    "alias": label.strip() or None,
                    "embed": False,
                    "line": number,
                    "raw": match.group(0),
                }
            )
    return links


def parse_note(source: str, path: str, text: str) -> Note:
    """Analiza una nota completa: metadatos, enlaces y fragmentos."""
    meta, body, consumed = parse_frontmatter(text)
    note_title = _scalar(
        str(meta.get("title") or os.path.splitext(os.path.basename(path))[0])
    )
    tags = _as_list(meta.get("tags"))
    for tag in inline_tags(body):
        if tag not in tags:
            tags.append(tag)

    lines = body.splitlines()
    body_line = consumed + 1
    stack: list[tuple[int, str]] = []
    chunks: list[Chunk] = []
    buffer: list[str] = []
    buffer_line = body_line
    heading = note_title

    def flush() -> None:
        nonlocal buffer
        raw = "\n".join(buffer).strip()
        if not raw:
            buffer = []
            return

        pieces = [(raw, buffer_line)]
        if len(raw) > MAX_CHARS:
            pieces = _split_long(raw, buffer_line, MAX_CHARS, OVERLAP_CHARS)

        for piece_index, (piece, line) in enumerate(pieces):
            piece = piece.strip()
            if not piece:
                continue
            if (
                len(piece) < MIN_CHARS
                and len(pieces) > 1
                and piece_index == len(pieces) - 1
            ):
                # Cola demasiado corta: se descarta en lugar de indexar ruido.
                continue
            chunks.append(
                Chunk(
                    source=source,
                    path=path,
                    line=line,
                    heading=heading,
                    text=piece,
                    note=note_title,
                    tags=list(tags),
                )
            )
        buffer = []

    for index, line in enumerate(lines):
        match = HEADING_RE.match(line)
        if match:
            flush()
            level = len(match.group(1))
            title = match.group(2).strip()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            heading = " > ".join(part for _, part in stack)
            buffer = [line]
            buffer_line = body_line + index
        else:
            if not buffer:
                buffer_line = body_line + index
            buffer.append(line)

    flush()
    return Note(
        source=source,
        path=path,
        title=note_title,
        tags=tags,
        links=extract_links(body, body_line, path),
        chunks=chunks,
        chars=len(text),
        words=len(body.split()),
    )


def chunk_note(source: str, path: str, text: str) -> list[Chunk]:
    """Trocea una nota en fragmentos con encabezado, línea y etiquetas."""
    return parse_note(source, path, text).chunks


def heading_path(chunk: Chunk) -> str:
    """Ruta de encabezados legible para mostrar en resultados."""
    return chunk.heading or chunk.note


def preview(chunk: Chunk, limit: int = 160) -> str:
    return _shorten(chunk.text, limit)
