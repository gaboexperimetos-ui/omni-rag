"""Configuración de omni-rag: fuentes, índice y backend de búsqueda."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_CONFIG = "~/.config/omni-rag/config.json"
DEFAULT_INDEX = "~/.local/share/omni-rag/index.json"

# Directorios que nunca se indexan aunque estén dentro de una fuente.
DEFAULT_EXCLUDES = (
    ".obsidian",
    ".git",
    ".trash",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".cache",
    ".next",
    "dist",
    "build",
    "target",
    "zig-cache",
    "zig-out",
)

TEXT_EXTENSIONS = (".md", ".markdown", ".mdx", ".txt")


def expand(path: str) -> Path:
    """Expande ~ y variables de entorno."""
    return Path(os.path.expandvars(os.path.expanduser(str(path))))


@dataclass
class Source:
    """Una raíz de documentos que omni-rag indexa."""

    name: str
    path: str
    type: str = "obsidian"
    exclude: list[str] = field(default_factory=list)
    include_extensions: list[str] = field(default_factory=lambda: list(TEXT_EXTENSIONS))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "type": self.type,
            "exclude": list(self.exclude),
            "include_extensions": list(self.include_extensions),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Source":
        return cls(
            name=str(data["name"]),
            path=str(data["path"]),
            type=str(data.get("type", "obsidian")),
            exclude=list(data.get("exclude", [])),
            include_extensions=list(data.get("include_extensions", TEXT_EXTENSIONS)),
        )


@dataclass
class Config:
    sources: list[Source] = field(default_factory=list)
    index_path: str = DEFAULT_INDEX
    backend: str = "bm25"
    k1: float = 1.5
    b: float = 0.75

    def to_dict(self) -> dict[str, Any]:
        return {
            "sources": [s.to_dict() for s in self.sources],
            "index_path": self.index_path,
            "backend": self.backend,
            "bm25": {"k1": self.k1, "b": self.b},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        bm25 = data.get("bm25", {})
        return cls(
            sources=[Source.from_dict(item) for item in data.get("sources", [])],
            index_path=str(data.get("index_path", DEFAULT_INDEX)),
            backend=str(data.get("backend", "bm25")),
            k1=float(bm25.get("k1", 1.5)),
            b=float(bm25.get("b", 0.75)),
        )

    def source(self, name: str) -> Source | None:
        for item in self.sources:
            if item.name == name:
                return item
        return None


def config_path(explicit: str | None = None) -> Path:
    if explicit:
        return expand(explicit)
    env = os.environ.get("OMNI_RAG_CONFIG")
    if env:
        return expand(env)
    return expand(DEFAULT_CONFIG)


def load(path: str | None = None) -> tuple[Config, Path]:
    """Carga la configuración; si no existe, devuelve una vacía."""
    target = config_path(path)
    if not target.exists():
        return Config(), target
    with target.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return Config.from_dict(data), target


def save(config: Config, path: str | None = None) -> Path:
    target = config_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(config.to_dict(), ensure_ascii=False, indent=2) + "\n"
    target.write_text(data, encoding="utf-8")
    return target
