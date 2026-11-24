# Cómo contribuir

Proyecto personal, pero las reglas son las de cualquier repo serio.

## Entorno

No hay dependencias. Python 3.10 o superior.

```bash
git clone git@github.com:gaboexperimetos-ui/omni-rag.git
cd omni-rag
make test
```

## Antes de abrir un PR

```bash
make compile
make test
```

Y si toca indexación o búsqueda, pruébalo sobre un vault real:

```bash
python3 -m omni_rag index
python3 -m omni_rag overview
python3 -m omni_rag search "algo que exista"
```

## Estilo

- Biblioteca estándar solamente. Si una dependencia parece necesaria, primero
  abre una idea y justifícala.
- Español en documentación y mensajes de usuario; inglés en nombres de código
  cuando el dominio lo pide (`chunk`, `index`, `backend`).
- Tipos en las firmas públicas, `from __future__ import annotations`.
- Nada de estado global fuera del registro de backends.
- Cada comportamiento nuevo lleva una prueba en `tests/`.

## Commits

Convención `tipo: resumen` (`feat`, `fix`, `docs`, `refactor`, `test`,
`chore`). Un commit, un cambio coherente. El cuerpo explica el porqué.

## Cambios de índice

`INDEX_VERSION` en `omni_rag/indexer.py` se sube cuando cambia el esquema del
JSON. Un índice con versión distinta se descarta y se reconstruye: no hay
migraciones. Si el cambio rompe la compatibilidad de configuración, dilo en el
PR y en el CHANGELOG.
