"""Interfaz de línea de comandos de omni-rag."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from . import config as cfg
from . import library as lib
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
    parser.add_argument("--source", help="filtrar por nombre de colección")
    parser.add_argument("--collection", dest="collection", help="alias de --source")
    parser.add_argument("--tag", help="filtrar por etiqueta")
    parser.add_argument("--path", help="filtrar por fragmento de ruta")


def _collection(args: argparse.Namespace) -> str | None:
    return getattr(args, "collection", None) or getattr(args, "source", None)


def _resolve_collections(config: Config, args: argparse.Namespace) -> set[str] | None:
    """Expande --collection (fuente o grupo) al conjunto de fuentes."""
    name = _collection(args)
    if not name:
        return None
    expanded = config.sources_for(name)
    if expanded is None:
        available = ", ".join(config.collection_names()) or "ninguna"
        print(
            f"omni-rag: no existe la colección {name!r} (disponibles: {available})",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return set(expanded)


def cmd_search(args: argparse.Namespace) -> int:
    config = _load_or_fail(args.config)
    _index_or_fail(config)
    hits = query(
        config,
        args.text,
        k=args.top,
        sources=_resolve_collections(config, args),
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
        sources=_resolve_collections(config, args),
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


# -- biblioteca ----------------------------------------------------------


def _catalog_or_fail(config_arg: str | None) -> lib.Catalog:
    config = _load_or_fail(config_arg)
    _index_or_fail(config)
    return lib.load(config)


def _find_or_fail(catalog: lib.Catalog, text: str) -> lib.NoteInfo:
    matches = catalog.find(text)
    if not matches:
        print(f"omni-rag: no encontré ninguna nota para {text!r}", file=sys.stderr)
        raise SystemExit(1)
    if len(matches) > 1:
        names = ", ".join(note.title for note in matches[:4])
        print(f"omni-rag: varias coincidencias ({names}…); uso la primera", file=sys.stderr)
    return matches[0]


def cmd_groups(args: argparse.Namespace) -> int:
    config, path = cfg.load(args.config)

    if args.action == "list":
        if not config.groups:
            print(f"sin grupos en {path}", file=sys.stderr)
            return 0
        for name, members in sorted(config.groups.items()):
            print(f"{name:16} → {', '.join(members)}")
        return 0

    if args.action == "add":
        if not args.name or not args.members:
            print("uso: omni-rag groups add NOMBRE FUENTE [FUENTE…]", file=sys.stderr)
            return 2
        if config.source(args.name):
            print(f"omni-rag: {args.name!r} ya es una fuente; elige otro nombre", file=sys.stderr)
            return 1
        unknown = [member for member in args.members if not config.source(member)]
        if unknown:
            print(
                f"omni-rag: fuentes desconocidas: {', '.join(unknown)}",
                file=sys.stderr,
            )
            return 1
        members: list[str] = []
        for member in args.members:
            if member not in members:
                members.append(member)
        config.groups[args.name] = members
        cfg.save(config, args.config)
        print(f"grupo {args.name} → {', '.join(members)}")
        print("el grupo es una vista: no hace falta reindexar")
        return 0

    if args.action == "remove":
        if not args.name:
            print("uso: omni-rag groups remove NOMBRE", file=sys.stderr)
            return 2
        if args.name not in config.groups:
            print(f"omni-rag: no existe el grupo {args.name!r}", file=sys.stderr)
            return 1
        del config.groups[args.name]
        cfg.save(config, args.config)
        print(f"grupo {args.name} quitado")
        return 0

    return 2


def cmd_collections(args: argparse.Namespace) -> int:
    catalog = _catalog_or_fail(args.config)
    rows = catalog.collections()

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    if not rows:
        print("sin colecciones", file=sys.stderr)
        return 0

    width = max(len(row["name"]) for row in rows)
    print(
        f"{'colección':<{width}}  {'tipo':<6}  {'notas':>6}  "
        f"{'palabras':>9}  {'tags':>5}  {'rojos':>6}"
    )
    for row in rows:
        print(
            f"{row['name']:<{width}}  {row['kind']:<6}  {row['notes']:>6}  "
            f"{row['words']:>9,}  {row['tags']:>5}  {row['broken']:>6}"
        )
    print()
    print("fuente = carpeta o vault; grupo = varias fuentes como una sola vista.")
    return 0


def cmd_overview(args: argparse.Namespace) -> int:
    catalog = _catalog_or_fail(args.config)
    summary = catalog.summary()

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    top = " · ".join(f"{tag} {count}" for tag, count in summary["top_tags"]) or "—"
    print("biblioteca omni-rag")
    print(f"  fuentes      {summary['sources']}")
    print(f"  notas        {summary['notes']}  ({summary['words']:,} palabras, {summary['chars']:,} chars)")
    print(f"  etiquetas    {summary['tags']}")
    print(f"  enlaces      {summary['links']}  ({summary['broken']} rojos, {summary['ambiguous']} ambiguos)")
    print(f"  huérfanas    {summary['orphans']}")
    print(f"  duplicadas   {summary['duplicates']}")
    print(f"  top etiquetas  {top}")
    return 0


def cmd_tags(args: argparse.Namespace) -> int:
    catalog = _catalog_or_fail(args.config)
    tags = catalog.tags()
    if args.json:
        print(json.dumps(
            [{"tag": tag, "notes": count} for tag, count in tags],
            ensure_ascii=False,
            indent=2,
        ))
        return 0
    if not tags:
        print("sin etiquetas", file=sys.stderr)
        return 0
    width = max(len(tag) for tag, _ in tags)
    for tag, count in tags[: args.limit or None]:
        print(f"{tag:<{width}}  {count}")
    return 0


def cmd_links(args: argparse.Namespace) -> int:
    catalog = _catalog_or_fail(args.config)
    note = _find_or_fail(catalog, args.note)
    outgoing = catalog.outgoing(note.key)
    incoming = catalog.backlinks(note.key)

    if args.json:
        payload = {
            "note": note.title,
            "location": note.location,
            "outgoing": [
                {
                    "target": link.target,
                    "line": link.line,
                    "status": link.status,
                    "resolved": link.resolved,
                }
                for link in outgoing
            ],
            "incoming": [
                {
                    "note": catalog.notes[origin].title,
                    "location": catalog.notes[origin].location,
                    "line": line,
                }
                for origin, line in incoming
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"{note.reference} — {note.location}")
    if note.tags:
        print(f"etiquetas: {', '.join(note.tags)}")

    if outgoing:
        print(f"\nsalientes ({len(outgoing)}):")
        for link in outgoing:
            suffix = f"  ← línea {link.line}"
            if link.status == "broken":
                suffix += "  [ROTO]"
            elif link.status == "ambiguous":
                suffix += f"  [AMBIGUO: {len(link.resolved)}]"
            elif link.status == "self":
                suffix += "  [a sí misma]"
            print(f"  → {link.target}{suffix}")
    else:
        print("\nsalientes (0)")

    if incoming:
        print(f"\nentrantes ({len(incoming)}):")
        for origin, line in incoming:
            source = catalog.notes.get(origin)
            title = source.title if source else origin
            print(f"  ← [[{title}]]  (línea {line})")
    else:
        print("\nentrantes (0)")
    return 0


def cmd_orphans(args: argparse.Namespace) -> int:
    catalog = _catalog_or_fail(args.config)
    orphans = catalog.orphans()
    if args.json:
        print(json.dumps(
            [{"note": note.title, "location": note.location} for note in orphans],
            ensure_ascii=False,
            indent=2,
        ))
        return 0
    if not orphans:
        print("no hay notas huérfanas")
        return 0
    for note in orphans:
        print(f"[[{note.title}]]  —  {note.location}")
    print(f"\n{len(orphans)} huérfanas", file=sys.stderr)
    return 0


def cmd_broken(args: argparse.Namespace) -> int:
    catalog = _catalog_or_fail(args.config)
    broken = catalog.broken()
    if args.json:
        print(json.dumps(
            [
                {
                    "from": link.origin_title,
                    "location": f"{link.origin_path}:{link.line}",
                    "target": link.target,
                }
                for link in broken
            ],
            ensure_ascii=False,
            indent=2,
        ))
        return 0
    if not broken:
        print("no hay enlaces rojos")
        return 0
    for link in broken:
        print(f"{link.origin_path}:{link.line}  →  {link.target}")
    print(f"\n{len(broken)} enlaces rojos", file=sys.stderr)
    return 0


def cmd_duplicates(args: argparse.Namespace) -> int:
    catalog = _catalog_or_fail(args.config)
    groups = catalog.duplicates()
    if args.json:
        print(json.dumps(
            [
                {
                    "title": notes[0].title,
                    "locations": [note.location for note in notes],
                }
                for _, notes in groups
            ],
            ensure_ascii=False,
            indent=2,
        ))
        return 0
    if not groups:
        print("no hay títulos duplicados")
        return 0
    for _, notes in groups:
        print(f"[[{notes[0].title}]]")
        for note in notes:
            print(f"  · {note.location}")
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

    overview = sub.add_parser("overview", help="resumen de la biblioteca")
    overview.add_argument("--json", action="store_true", help="salida JSON")
    overview.set_defaults(func=cmd_overview)

    collections = sub.add_parser(
        "collections", help="resumen por colección (materias, vaults, proyectos)"
    )
    collections.add_argument("--json", action="store_true", help="salida JSON")
    collections.set_defaults(func=cmd_collections)

    groups = sub.add_parser("groups", help="grupos de colecciones (colegio = materias)")
    groups_sub = groups.add_subparsers(dest="action", required=True)
    groups_list = groups_sub.add_parser("list", help="lista los grupos")
    groups_list.set_defaults(func=cmd_groups)
    groups_add = groups_sub.add_parser("add", help="crea o reemplaza un grupo")
    groups_add.add_argument("name")
    groups_add.add_argument("members", nargs="+", metavar="FUENTE")
    groups_add.set_defaults(func=cmd_groups)
    groups_remove = groups_sub.add_parser("remove", help="quita un grupo")
    groups_remove.add_argument("name")
    groups_remove.set_defaults(func=cmd_groups)

    tags = sub.add_parser("tags", help="etiquetas de la biblioteca y su uso")
    tags.add_argument("--json", action="store_true", help="salida JSON")
    tags.add_argument("--limit", type=int, default=0, help="máximo de etiquetas")
    tags.set_defaults(func=cmd_tags)

    links = sub.add_parser("links", help="enlaces salientes y entrantes de una nota")
    links.add_argument("note", help="título o ruta de la nota")
    links.add_argument("--json", action="store_true", help="salida JSON")
    links.set_defaults(func=cmd_links)

    orphans = sub.add_parser("orphans", help="notas sin enlaces")
    orphans.add_argument("--json", action="store_true", help="salida JSON")
    orphans.set_defaults(func=cmd_orphans)

    broken = sub.add_parser("broken", help="enlaces a notas que no existen")
    broken.add_argument("--json", action="store_true", help="salida JSON")
    broken.set_defaults(func=cmd_broken)

    duplicates = sub.add_parser("duplicates", help="títulos repetidos")
    duplicates.add_argument("--json", action="store_true", help="salida JSON")
    duplicates.set_defaults(func=cmd_duplicates)

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
