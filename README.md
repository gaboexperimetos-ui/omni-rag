# omni-rag

Biblioteca unificada de notas Markdown/Obsidian, con motor de búsqueda léxica
(BM25) sin dependencias, sin GPU y sin red. Indexa varias colecciones —una
materia, un curso, un proyecto, un vault entero— en un solo catálogo, y expone
sobre ellas búsqueda, enlaces, etiquetas y salud del grafo. La respuesta la
escribe después un LLM, si la quieres; omni-rag recupera y cita.

## Qué es BM25

BM25 es una función de puntuación, no un modelo. Para cada consulta y cada
fragmento combina:

- **TF** — cuántas veces aparece el término en el fragmento, con saturación
  (`k1`): repetirlo 50 veces no vale 50 veces más.
- **IDF** — cuánto destaca el término en el corpus: "GPU" pesa más que "nota"
  porque aparece en menos fragmentos.
- **Longitud** (`b`) — normaliza por tamaño, para que un fragmento largo no gane
  solo por ser largo.

Ventajas: cero dependencias, resultados reproducibles, latencia de
milisegundos, funciona con 22 notas o con 20 000 y no alucina: si no hay
coincidencia, no devuelve nada. Límite: no entiende sinónimos ni paráfrasis
("coche" no encuentra "automóvil").

## Instalación

No hace falta instalar nada: el paquete no tiene dependencias.

```bash
cd ~/proyectos/omni-rag
python3 -m omni_rag init --vault ~/SegundoCerebro --name cerebro
python3 -m omni_rag index
python3 -m omni_rag search "qué modelo local uso"
```

Opcional, para tener el comando `omni-rag` en el PATH:

```bash
python3 -m pip install --user -e .
```

## Uso

```bash
omni-rag init [--vault RUTA] [--name NOMBRE]   # crea ~/.config/omni-rag/config.json
omni-rag index [--force]                       # indexa; incremental por mtime
omni-rag search "consulta" [-k 5] [--json]     # resultados con cita
omni-rag context "consulta" [--tokens 4000]    # bloque listo para un LLM
omni-rag sources add|list|remove               # colecciones (vaults, carpetas)
omni-rag collections                           # notas/palabras/tags por colección
omni-rag overview                              # salud global de la biblioteca
omni-rag tags [--limit N]                      # etiquetas y cuántas notas las usan
omni-rag links "NOTA"                          # salientes, entrantes y estado
omni-rag orphans                               # notas sin enlaces
omni-rag broken                                # enlaces a notas inexistentes
omni-rag duplicates                            # títulos repetidos
omni-rag stats                                 # estado del índice
```

Filtros en `search` y `context`: `--collection cerebro`, `--tag ia`,
`--path proyectos`. `--source` sigue valiendo como alias de `--collection`.

### Ejemplo de `context`

```bash
omni-rag context "cómo arranco el router local" --tokens 2000
```

Devuelve bloques numerados con `[[nota]]`, ruta, línea y encabezado, listos
para pegar en un prompt. La generación no la hace omni-rag.

## Cómo crece: de una materia al omni

La unidad es la **colección**. Cada colección es una carpeta o vault; el
catálogo es uno solo y se filtra por colección. Eso permite la progresión sin
duplicar índices ni código:

```bash
# 1) una materia
omni-rag sources add matematicas ~/Colegio/Matematicas
omni-rag index
omni-rag search "derivadas" --collection matematicas
omni-rag context "derivadas" --collection matematicas --tokens 2000

# 2) todas las materias del colegio
omni-rag sources add fisica     ~/Colegio/Fisica
omni-rag sources add historia   ~/Colegio/Historia
omni-rag index
omni-rag collections            # una fila por materia
omni-rag search "revolución" --collection historia

# 3) el colegio completo y la vida: el omni
omni-rag sources add colegio    ~/Colegio
omni-rag sources add vida       ~/Vida
omni-rag index
omni-rag overview               # todo junto
```

Cada fila de `collections` es tu "RAG de la materia": mismo motor, mismo
formato de citas, distinto filtro. El omni es la misma biblioteca sin filtro.
Cuando una colección crezca demasiado, se puede mover a su propio índice y
enchufarla como backend; el contrato de salida no cambia.

## Configuración

`~/.config/omni-rag/config.json` (o `--config RUTA`, o `OMNI_RAG_CONFIG`):

```json
{
  "sources": [
    { "name": "cerebro", "path": "~/SegundoCerebro", "type": "obsidian" },
    { "name": "docs",    "path": "~/Documentos",    "type": "dir",
      "exclude": ["*.bak.md"] }
  ],
  "index_path": "~/.local/share/omni-rag/index.json",
  "backend": "bm25",
  "bm25": { "k1": 1.5, "b": 0.75 }
}
```

- `type: obsidian` → los resultados se citan como `[[nota]]`.
- `type: dir` → se citan como `fuente/ruta`.
- Extensiones indexadas: `.md`, `.markdown`, `.mdx`, `.txt`.
- Se ignoran `.obsidian/`, `.git/`, `.trash/`, `node_modules/`, `__pycache__/`,
  `dist/`, `build/`, `target/`, `zig-*` y todo lo que empiece por punto.

El índice vive fuera del repo (`~/.local/share/omni-rag/index.json`) y se
reconstruye solo lo que cambió (mismo `mtime_ns` y tamaño).

## Arquitectura

```
omni_rag/
├── tokenize.py   normalización, stopwords, stemming ligero español
├── chunker.py    frontmatter YAML, secciones, enlaces, metadatos
├── bm25.py       BM25 Okapi + campos ponderados (título/tags/encabezado)
├── indexer.py    recorrido de colecciones, índice JSON incremental
├── library.py    catálogo: notas, etiquetas, enlaces, huérfanas, duplicados
├── backends.py   registro de recuperadores enchufables
├── search.py     filtros, snippets, bloque de contexto
└── cli.py        interfaz de línea de comandos
```

### Añadir un backend futuro

`backends.py` es el punto de enchufe. Un backend solo tiene que devolver
`(puntuación, fragmento)` ordenados:

```python
from .backends import register

@register("embeddings")
class EmbeddingsRetriever:
    name = "embeddings"

    def __init__(self, index, **options):
        ...

    def search(self, query, k=5):
        ...
```

Después se activa con `"backend": "embeddings"` en la config. El CLI y el
formato de salida no cambian. Ese es el sitio para conectar el "principal" con
RAGs nuevos (vectorial, un servicio HTTP, un servidor MCP…).

## Estado

- [x] BM25 multi-fuente con índice incremental
- [x] Catálogo de biblioteca: etiquetas, enlaces, huérfanas, rojos, duplicados
- [x] Colecciones filtrables (`--collection`) con resumen por colección
- [x] Filtros por fuente, etiqueta y ruta
- [x] Salida humana, JSON y bloque de contexto
- [ ] Backend de embeddings (requiere modelo aparte; el router local no expone
      `/v1/embeddings`)
- [ ] Respuesta automática con el modelo local (`--ask`)

## Pruebas

```bash
python3 -m unittest discover -s tests -v
```
