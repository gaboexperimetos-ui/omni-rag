# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
Versionado [SemVer](https://semver.org/lang/es/).

## [0.2.0] — 2026-11-24

### Añadido

- Catálogo de biblioteca sobre el índice: notas, etiquetas, palabras y enlaces.
- Resolución de wikilinks y enlaces Markdown relativos con estado
  `ok` / `broken` / `ambiguous` / `self`.
- Comandos `overview`, `collections`, `tags`, `links`, `orphans`, `broken`,
  `duplicates`.
- Filtro `--collection` en `search` y `context` (alias de `--source`).
- Exclusión por defecto de plantillas de Obsidian (`_plantillas`,
  `_templates`, `templates`).
- Estructura de proyecto: CI, plantillas de issue/PR, docs, ejemplos,
  Makefile, licencia MIT y lanzador `bin/omni-rag`.

### Cambiado

- Índice en versión 2: cada archivo guarda metadatos de nota además de
  fragmentos. El índice anterior se reconstruye solo.
- `chunker.py` expone `parse_note()`; `chunk_note()` se mantiene.

## [0.1.0] — 2026-11-24

### Añadido

- Tokenizador español sin dependencias: acentos, stopwords y stemming ligero.
- Troceado por encabezados con frontmatter YAML y solape.
- BM25 Okapi con título, etiquetas y encabezados ponderados.
- Índice JSON incremental por `mtime` y tamaño.
- CLI: `init`, `index`, `search`, `context`, `sources`, `stats`.
- Registro de backends para embeddings o servicios futuros.
- 17 pruebas con `unittest`.
