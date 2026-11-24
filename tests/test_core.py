"""Pruebas del núcleo de omni-rag (solo biblioteca estándar)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from omni_rag.bm25 import BM25, weighted_tokens
from omni_rag.chunker import chunk_note, parse_frontmatter
from omni_rag.config import Config, Source
from omni_rag.indexer import build, load_index
from omni_rag.search import context_block, format_hits, hits_to_json, query
from omni_rag.tokenize import stem, strip_accents, tokenize


class TokenizeTest(unittest.TestCase):
    def test_strips_accents(self) -> None:
        self.assertEqual(strip_accents("Búsqueda rápida"), "Busqueda rapida")

    def test_drops_stopwords(self) -> None:
        self.assertEqual(tokenize("el modelo de la casa"), ["model", "casa"])

    def test_keeps_short_nouns_distinct(self) -> None:
        self.assertNotEqual(stem("casa"), stem("caso"))

    def test_singular_and_plural_converge(self) -> None:
        self.assertEqual(stem("modelo"), stem("modelos"))
        self.assertEqual(stem("configuracion"), stem("configuraciones"))
        self.assertEqual(stem("indexar"), stem("indexando"))

    def test_wikilinks_are_searchable_by_name(self) -> None:
        self.assertIn(stem("llama"), tokenize("Ver [[llama.cpp]] para más datos"))


class ChunkerTest(unittest.TestCase):
    def test_frontmatter_is_parsed(self) -> None:
        meta, body, consumed = parse_frontmatter(
            '---\ntitle: "Mi nota"\ntags: [estudio, ia]\n---\nCuerpo\n'
        )
        self.assertEqual(meta["title"], "Mi nota")
        self.assertEqual(meta["tags"], ["estudio", "ia"])
        self.assertEqual(body.strip(), "Cuerpo")
        self.assertEqual(consumed, 4)

    def test_sections_carry_heading_path(self) -> None:
        text = (
            "---\ntitle: Nota\ntags: [ia]\n---\n"
            "# Introducción\n\nTexto inicial.\n\n"
            "## Detalle\n\nMás texto sobre el tema.\n"
        )
        chunks = chunk_note("test", "nota.md", text)
        headings = [chunk.heading for chunk in chunks]
        self.assertIn("Introducción", headings)
        self.assertIn("Introducción > Detalle", headings)
        self.assertTrue(all(chunk.note == "Nota" for chunk in chunks))
        self.assertTrue(all(chunk.tags == ["ia"] for chunk in chunks))

    def test_long_sections_are_split(self) -> None:
        text = "# Largo\n\n" + "\n\n".join(
            f"Párrafo número {i}." for i in range(200)
        )
        chunks = chunk_note("test", "largo.md", text)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk.text) <= 1000 for chunk in chunks))


class Bm25Test(unittest.TestCase):
    def test_rare_term_outranks_common_term(self) -> None:
        corpus = [
            ["modelo", "local", "rapido"],
            ["modelo", "local", "lento"],
            ["modelo", "local", "estable"],
            ["modelo", "local", "estable"],
            ["otro", "tema", "distinto"],
        ]
        bm25 = BM25(corpus)
        scores = bm25.scores(["modelo", "distinto"])
        common = max(scores[:4])
        rare = scores[4]
        self.assertGreater(rare, common)

    def test_weighted_tokens_boost_title(self) -> None:
        tokens = weighted_tokens("cuerpo", title="título", tags=["etiqueta"])
        self.assertGreater(tokens.count(stem("titulo")), tokens.count(stem("cuerpo")))

    def test_empty_query_scores_zero(self) -> None:
        bm25 = BM25([["uno"], ["dos"]])
        self.assertEqual(bm25.scores([]), [0.0, 0.0])


class IntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.vault = self.root / "vault"
        self.vault.mkdir()
        (self.vault / "ia.md").write_text(
            '---\ntitle: "IA local"\ntags: [ia]\n---\n'
            "# IA local\n\nEl modelo local corre en una GPU RTX 3060.\n",
            encoding="utf-8",
        )
        (self.vault / "estudio.md").write_text(
            '---\ntitle: "Estudio"\ntags: [estudio]\n---\n'
            "# Estudio\n\nApuntes de cálculo diferencial y álgebra.\n",
            encoding="utf-8",
        )
        (self.vault / ".obsidian").mkdir()
        (self.vault / ".obsidian" / "basura.md").write_text("no indexar", encoding="utf-8")

        self.config = Config(
            sources=[Source(name="vault", path=str(self.vault), type="obsidian")],
            index_path=str(self.root / "index.json"),
        )
        build(self.config, force=True)
        self.index = load_index(Path(self.config.index_path))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_hidden_vault_dirs_are_ignored(self) -> None:
        files = self.index["files"]
        self.assertEqual(len(files), 2)
        self.assertNotIn("vault:.obsidian/basura.md", files)

    def test_query_finds_note(self) -> None:
        hits = query(self.config, "GPU", k=3)
        self.assertTrue(hits)
        self.assertEqual(hits[0].chunk.note, "IA local")
        self.assertEqual(hits[0].kind, "obsidian")
        self.assertIn("[[IA local]]", format_hits(hits, "GPU"))

    def test_tag_filter(self) -> None:
        hits = query(self.config, "apuntes cálculo", k=3, tag="estudio")
        self.assertTrue(hits)
        self.assertTrue(all("estudio" in hit.chunk.tags for hit in hits))

    def test_source_filter_excludes_everything_else(self) -> None:
        hits = query(self.config, "GPU", k=3, source="otra")
        self.assertEqual(hits, [])

    def test_context_respects_budget(self) -> None:
        hits = query(self.config, "modelo GPU cálculo", k=3)
        block = context_block(hits, max_tokens=100, max_chars_per_chunk=500)
        self.assertLessEqual(len(block), 100 * 4 + 200)

    def test_json_output_is_valid(self) -> None:
        hits = query(self.config, "GPU", k=1)
        payload = json.loads(hits_to_json(hits, "GPU"))
        self.assertEqual(payload[0]["note"], "IA local")


if __name__ == "__main__":
    unittest.main()
