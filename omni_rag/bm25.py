"""BM25 Okapi implementado sobre la biblioteca estándar.

BM25 puntúa un documento para una consulta combinando tres señales:

- TF: cuántas veces aparece cada término en el documento (con saturación, para
  que repetir una palabra 50 veces no valga 50 veces más).
- IDF: cuánto destaca ese término en el corpus; las palabras que salen en todas
  las notas pesan poco y las raras pesan mucho.
- Longitud: normaliza por el tamaño del documento (``b``), para que una nota
  larga no gane solo por ser larga.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Iterable, Sequence


class BM25:
    """Índice invertido BM25 sobre una lista de documentos ya tokenizados."""

    def __init__(self, documents: Sequence[Sequence[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.documents = [list(doc) for doc in documents]
        self.n_docs = len(self.documents)

        self.term_freqs: list[Counter[str]] = [Counter(doc) for doc in self.documents]
        self.doc_lengths = [len(doc) for doc in self.documents]
        self.avg_length = (sum(self.doc_lengths) / self.n_docs) if self.n_docs else 0.0

        self.doc_freq: Counter[str] = Counter()
        for freq in self.term_freqs:
            self.doc_freq.update(freq.keys())

        self._idf: dict[str, float] = {}

    def idf(self, term: str) -> float:
        """IDF suavizado, siempre positivo (variante Robertson/Sparck Jones)."""
        cached = self._idf.get(term)
        if cached is not None:
            return cached
        df = self.doc_freq.get(term, 0)
        value = math.log(1.0 + (self.n_docs - df + 0.5) / (df + 0.5))
        self._idf[term] = value
        return value

    def scores(self, query: Sequence[str]) -> list[float]:
        """Puntuación de cada documento para la consulta dada."""
        results = [0.0] * self.n_docs
        if not self.n_docs or not query:
            return results

        for term in query:
            df = self.doc_freq.get(term, 0)
            if df == 0:
                continue
            idf = self.idf(term)
            for index, freq in enumerate(self.term_freqs):
                tf = freq.get(term, 0)
                if not tf:
                    continue
                norm = self.k1 * (
                    1.0 - self.b + self.b * (self.doc_lengths[index] / (self.avg_length or 1.0))
                )
                results[index] += idf * (tf * (self.k1 + 1.0)) / (tf + norm)
        return results

    def score_document(self, query: Sequence[str], document: Sequence[str]) -> float:
        """Puntúa un documento suelto contra el corpus ya indexado."""
        if not self.n_docs or not query:
            return 0.0
        freq = Counter(document)
        length = len(document)
        total = 0.0
        for term in query:
            tf = freq.get(term, 0)
            if not tf or term not in self.doc_freq:
                continue
            norm = self.k1 * (
                1.0 - self.b + self.b * (length / (self.avg_length or 1.0))
            )
            total += self.idf(term) * (tf * (self.k1 + 1.0)) / (tf + norm)
        return total


def weighted_tokens(
    text: str,
    *,
    title: str = "",
    heading: str = "",
    tags: Iterable[str] = (),
) -> list[str]:
    """Construye la bolsa de términos de un fragmento con campos ponderados.

    El título y las etiquetas pesan más que el cuerpo porque describen el tema
    de la nota; los encabezados pesan algo menos que el título.
    """
    from .tokenize import tokenize

    tokens = tokenize(text)
    title_tokens = tokenize(title)
    heading_tokens = tokenize(heading)
    tag_tokens = tokenize(" ".join(tags))

    return title_tokens * 3 + tag_tokens * 3 + heading_tokens * 2 + tokens
