"""Normalización y tokenización sin dependencias externas.

Pensado para español: quita acentos, descarta palabras vacías y aplica un
stemming ligero. No busca lingüística perfecta; busca que "modelos", "modelo"
y "modelación" caigan en la misma raíz de búsqueda.
"""

from __future__ import annotations

import re
import unicodedata

_WORD_RE = re.compile(r"[0-9a-z]+")
_WIKILINK_RE = re.compile(r"\[\[([^\]|#]*)(?:#[^\]|]*)?(?:\|([^\]]*))?\]\]")
_MDLINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_URL_RE = re.compile(r"https?://\S+")
_TAG_RE = re.compile(r"(?<![\w#])#([A-Za-z0-9_][A-Za-z0-9_/-]*)")

STOPWORDS = frozenset(
    """
    a al algo algun alguna algunas alguno algunos ante antes aqui asi aun cada
    como con contra cual cuales cuando de del desde donde dos el ella ellas
    ellos en entre era eres es esa esas ese eso esos esta estaba estan estas
    este esto estos estoy fue fueron ha haber habia han has hasta hay he la
    las le les lo los mas me mi mis mucho muy nada ni no nos nosotros o os
    otra otro para pero poco por porque que quien se sea segun ser si sin sobre
    son su sus tambien tan te tengo ti tiene tienen todo todos tu tus un una
    unas uno unos usted ustedes y ya yo

    the and for with that this from you your are was were have has not but they
    what when which who will can all any how its into our out their there these
    those them then than too very just also
    """.split()
)

# Sufijos en orden de mayor a menor longitud. Se aplican en bucle para que
# "modelos" -> "modelo" -> "model" y "modelo" -> "model" converjan.
# Las vocales finales van al final para no comerse palabras antes de probar
# los sufijos largos. Se exige una raíz de al menos 3 caracteres.
_SUFFIXES = (
    "aciones",
    "iciones",
    "uciones",
    "amente",
    "idades",
    "ciones",
    "iendo",
    "acion",
    "icion",
    "ucion",
    "mente",
    "idad",
    "ando",
    "ados",
    "idos",
    "ado",
    "ido",
    "ar",
    "es",
    "s",
    "o",
    "a",
)

_MIN_ROOT = 4


def strip_accents(text: str) -> str:
    """Devuelve el texto sin diacríticos (ñ -> n, á -> a)."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def unmark_markdown(text: str) -> str:
    """Quita sintaxis de Markdown/Obsidian conservando el texto útil.

    Los wikilinks se expanden a su alias o destino para que una nota enlazada
    sea buscable por su nombre.
    """
    text = _URL_RE.sub(" ", text)
    text = _WIKILINK_RE.sub(lambda m: m.group(2) or m.group(1) or " ", text)
    text = _MDLINK_RE.sub(lambda m: m.group(1), text)
    text = text.replace("`", " ")
    return text


def inline_tags(text: str) -> list[str]:
    """Extrae etiquetas tipo #estudio de un texto Markdown."""
    tags = []
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            # Un encabezado no es una etiqueta.
            line = line.lstrip().lstrip("#")
        for match in _TAG_RE.finditer(line):
            tag = match.group(1).lower()
            if tag not in tags:
                tags.append(tag)
    return tags


def stem(word: str) -> str:
    """Stemming ligero e iterativo, sobre texto sin acentos y en minúsculas.

    Repite la poda de sufijos hasta que ninguno aplique. Así "modelos" y
    "modelo" acaban en la misma raíz, que es lo que importa para recuperar.
    Las palabras de 4 letras o menos se dejan intactas para no mezclar
    sustantivos cortos distintos ("casa" / "caso").
    """
    if len(word) <= 4:
        return word
    current = word
    changed = True
    while changed:
        changed = False
        for suffix in _SUFFIXES:
            candidate = current[: -len(suffix)]
            if current.endswith(suffix) and len(candidate) >= _MIN_ROOT:
                current = candidate
                changed = True
                break
    return current


def tokenize(text: str, *, keep_stopwords: bool = False) -> list[str]:
    """Convierte texto en una lista de términos normalizados.

    Args:
        text: texto de entrada, puede llevar Markdown.
        keep_stopwords: si es True no filtra palabras vacías (útil para
            construir frases exactas).
    """
    if not text:
        return []
    clean = strip_accents(unmark_markdown(text)).lower()
    tokens = []
    for raw in _WORD_RE.findall(clean):
        if len(raw) == 1 and not raw.isdigit():
            continue
        if not keep_stopwords and raw in STOPWORDS:
            continue
        tokens.append(stem(raw))
    return tokens


def unique_terms(text: str) -> list[str]:
    """Términos sin repetir, en orden de aparición."""
    seen: list[str] = []
    for term in tokenize(text):
        if term not in seen:
            seen.append(term)
    return seen


def normalize_phrase(text: str) -> str:
    """Frase normalizada para comparaciones de coincidencia exacta."""
    clean = strip_accents(text).lower()
    return " ".join(_WORD_RE.findall(clean))
