"""Interfaz de línea de comandos de omni-rag."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from . import config as cfg
from .backends import available as available_backends
from .config import Config, Source, expand
from .indexer import build, load_index, stats as index_stats
from .search import context_block, format_hits, hits_to_json, query


def _load_or_fail(config_arg: str | None) -> Config:
    config, path = cfg.load(config_arg)
    if not config.sources:
        print(
            f"omni-rag: no hay fuentes configuradas en {path}\n"
            "Crea la configuración con:  omni-rag init",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return config


def _index_or_fail(config: Config) -> dict:
    index = load_index(expand(config.index_path))
    if not index.get("files"):
        print(
            "omni-rag: el índice está vacío.\n"
            "Constrúyelo con:  omni-rag index",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return index


def cmd_init(args: argparse.Namespace) -> int:
    config, path = cfg.load(args.config)

    if args.vault:
        vault = Path(args.vault).expanduser()
        if not vault.is_dir():
            print(f"omni-rag: la ruta no es un directorio: {vault}", file=sys.stderr)
            return 1
        name = args.name or vault.resolve().name.lower().replace(" ", "-")
        if not config.source(name):
            config.sources.append(Source(name=name, path=str(vault), type="obsidian"))

    if not config.sources:
        default = Path.home() / "SegundoCerebro"
        if default.is_dir():
            config.sources.append(
                Source(name="cerebro", path=str(default), type="obsidian")
            )

    target = cfg.save(config, args.config)
    print(f"config: {target}")
    if not config.sources:
        print("Añade una fuente:  omni-rag sources add NOMBRE /ruta/al/vault")
    for source in config.sources:
        print(f"  · {source.name} → {source.path}  ({source.type})")
    print(f"índice: {expand(config.index_path)}")
    return 0


def cmd_index(args: argparse.Namespace) -> int:
    config = _load_or_fail(args.config)

    def progress(message: str) -> None:
        print(message, file=sys.stderr)

    index = build(config, force=args.force, progress=progress)
    summary = index_stats(index)
    print(
        f"indexado: {summary['files']} archivos, {summary['chunks']} fragmentos "
        f"({summary['chars']:,} chars)"
    )
    print(f"índice: {expand(config.index_path)}")
    if summary["errors"]:
        print(f"avisos: {len(summary['errors'])} (ver stats)", file=sys.stderr)
    return 0


def _common_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-k", "--top", type=int, default=5, help="resultados (5)")
    parser.add_argument("--source", help="filtrar por nombre de fuente")
    parser.add_argument("--tag", help="filtrar por etiqueta")
    parser.add_argument("--path", help="filtrar por fragmento de ruta")


def cmd_search(args: argparse.Namespace) -> int:
    config = _load_or_fail(args.config)
    _index_or_fail(config)
    hits = query(
        config,
        args.text,
        k=args.top,
        source=args.source,
        tag=args.tag,
        path=args.path,
    )
    if args.json:
        print(hits_to_json(hits, args.text))
    elif not hits:
        print("sin resultados", file=sys.stderr)
    else:
        print(format_hits(hits, args.text))
    return 0


def cmd_context(args: argparse.Namespace) -> int:
    config = _load_or_fail(args.config)
    _index_or_fail(config)
    hits = query(
        config,
        args.text,
        k=args.top,
        source=args.source,
        tag=args.tag,
        path=args.path,
    )
    if not hits:
        print("sin resultados", file=sys.stderr)
        return 0
    print(
        context_block(
            hits,
            max_tokens=args.tokens,
            max_chars_per_chunk=args.max_chars,
        )
    )
    return 0


def cmd_sources(args: argparse.Namespace) -> int:
    config, path = cfg.load(args.config)

    if args.action == "list":
        if not config.sources:
            print(f"sin fuentes en {path}", file=sys.stderr)
        for source in config.sources:
            print(f"{source.name:16} {source.type:9} {source.path}")
        return 0

    if args.action == "add":
        if not args.name or not args.path:
            print("uso: omni-rag sources add NOMBRE /ruta", file=sys.stderr)
            return 2
        root = Path(args.path).expanduser()
        if not root.is_dir():
            print(f"omni-rag: la ruta no es un directorio: {root}", file=sys.stderr)
            return 1
        if config.source(args.name):
            print(f"omni-rag: ya existe una fuente llamada {args.name!r}", file=sys.stderr)
            return 1
        config.sources.append(
            Source(
                name=args.name,
                path=str(root),
                type=args.type,
                exclude=list(args.exclude or []),
            )
        )
        target = cfg.save(config, args.config)
        print(f"añadida {args.name} → {root}  ({target})")
        print("reindexa con:  omni-rag index")
        return 0

    if args.action == "remove":
        if not args.name:
            print("uso: omni-rag sources remove NOMBRE", file=sys.stderr)
            return 2
        before = len(config.sources)
        config.sources = [s for s in config.sources if s.name != args.name]
        if len(config.sources) == before:
            print(f"omni-rag: no existe la fuente {args.name!r}", file=sys.stderr)
            return 1
        cfg.save(config, args.config)
        print(f"quitada {args.name}; reindexa con:  omni-rag index")
        return 0

    return 2


def cmd_stats(args: argparse.Namespace) -> int:
    config, path = cfg.load(args.config)
    index = load_index(expand(config.index_path))
    summary = index_stats(index)
    print(f"config:    {path}")
    print(f"índice:    {expand(config.index_path)}")
    print(f"backend:   {config.backend} (disponibles: {', '.join(available_backends())})")
    print(f"construido: {summary['built_at'] or '—'}")
    print(f"fuentes:   {summary['sources']}")
    print(f"archivos:  {summary['files']}")
    print(f"fragmentos:{summary['chunks']}")
    print(f"caracteres:{summary['chars']:,} (mediana {summary['median_chars']})")
    for error in summary["errors"]:
        print(f"aviso: {error}", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="omni-rag",
        description="RAG léxico (BM25) multi-fuente sobre notas Markdown.",
    )
    parser.add_argument("--config", help="ruta alternativa a config.json")
    parser.add_argument("--version", action="version", version=f"omni-rag {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="crea la configuración inicial")
    init.add_argument("--vault", help="ruta del vault a añadir")
    init.add_argument("--name", help="nombre de la fuente (por defecto, la carpeta)")
    init.set_defaults(func=cmd_init)

    index = sub.add_parser("index", help="construye o actualiza el índice")
    index.add_argument("--force", action="store_true", help="reindexar todo")
    index.set_defaults(func=cmd_index)

    search = sub.add_parser("search", help="busca y muestra resultados")
    search.add_argument("text")
    search.add_argument("--json", action="store_true", help="salida JSON")
    _common_filters(search)
    search.set_defaults(func=cmd_search)

    context = sub.add_parser("context", help="bloque de contexto para un LLM")
    context.add_argument("text")
    context.add_argument("--tokens", type=int, default=4000, help="presupuesto (4000)")
    context.add_argument("--max-chars", type=int, default=1200, help="por fragmento")
    _common_filters(context)
    context.set_defaults(func=cmd_context)

    sources = sub.add_parser("sources", help="gestiona las fuentes")
    sources_sub = sources.add_subparsers(dest="action", required=True)
    sources_list = sources_sub.add_parser("list", help="lista las fuentes")
    sources_list.set_defaults(func=cmd_sources)
    sources_add = sources_sub.add_parser("add", help="añade una fuente")
    sources_add.add_argument("name")
    sources_add.add_argument("path")
    sources_add.add_argument("--type", default="obsidian", help="obsidian | dir")
    sources_add.add_argument("--exclude", action="append", help="patrón a excluir")
    sources_add.set_defaults(func=cmd_sources)
    sources_remove = sources_sub.add_parser("remove", help="quita una fuente")
    sources_remove.add_argument("name")
    sources_remove.set_defaults(func=cmd_sources)

    stats = sub.add_parser("stats", help="estado del índice")
    stats.set_defaults(func=cmd_stats)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
