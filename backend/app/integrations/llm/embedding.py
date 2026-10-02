"""Deterministic local text embeddings.

Groq serves chat completions, not embeddings, and the semantic cache needs an
embedder that is cheap, offline, stable across restarts and identical between
development and CI. A hashed character/word n-gram projection satisfies all
four: the same string always produces the same vector, no key is required, and
``make dev`` works with no network at all (section 41).

This is a real feature-hashing embedder - sublinear signed hashing into a fixed
space, sublinear term weighting, L2 normalised - not a placeholder. It is
deliberately paired with the deterministic entity/numeral guard in section 17,
which is what actually prevents ``iphone 16`` matching ``iphone 17``: cosine
similarity alone is never trusted to make that call.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from functools import lru_cache

from app.core.config import settings

DIM = settings.embedding_dim

_WORD = re.compile(r"[a-z0-9]+(?:[.'-][a-z0-9]+)*")
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "how",
        "i",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "to",
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "will",
        "with",
        "you",
        "your",
        "me",
        "my",
        "our",
        "us",
        "do",
        "does",
        "did",
        "can",
        "could",
        "should",
        "would",
        "about",
        "into",
        "over",
        "under",
        "near",
    ]
)


def normalize_text(text: str) -> str:
    """Lowercase, strip accents, collapse whitespace."""
    folded = unicodedata.normalize("NFKD", text or "")
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", folded.strip().lower())


def tokenize(text: str) -> list[str]:
    return _WORD.findall(normalize_text(text))


def content_tokens(text: str) -> list[str]:
    return [t for t in tokenize(text) if t not in _STOPWORDS]


def _features(text: str) -> dict[str, float]:
    """Order-insensitive content features.

    Three families, deliberately weighted:

    * content-word unigrams carry most of the mass, so dropping a stopword or
      reordering words does not move the vector
    * unordered word pairs add a little phrase structure without re-introducing
      word-order sensitivity
    * per-token character trigrams absorb plurals and small spelling drift

    Character n-grams are taken *within* a token rather than across the joined
    string. Spanning them across words makes similarity depend on word order,
    which would mean "cafes in Koramangala" and "Koramangala cafes" - the same
    query - score as unrelated, and the semantic layer would never fire.
    """
    tokens = content_tokens(text) or tokenize(text)
    counts: dict[str, float] = {}

    for token in tokens:
        counts["w:" + token] = counts.get("w:" + token, 0.0) + 1.0

    # Unordered pairs: {a,b} and {b,a} hash to the same feature.
    for i, first in enumerate(tokens):
        for second in tokens[i + 1 : i + 4]:
            a, b = sorted((first, second))
            key = "p:" + a + "_" + b
            counts[key] = counts.get(key, 0.0) + 0.4

    for token in tokens:
        padded = "^" + token + "$"
        for i in range(max(0, len(padded) - 2)):
            key = "c:" + padded[i : i + 3]
            counts[key] = counts.get(key, 0.0) + 0.25

    # Sublinear term frequency: a term repeated ten times is not ten times as
    # informative as one seen once.
    return {k: 1.0 + math.log(v) if v > 1 else v for k, v in counts.items()}


def _hash_index(feature: str) -> tuple[int, float]:
    digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
    value = int.from_bytes(digest, "big")
    bucket = value % DIM
    sign = 1.0 if (value >> 63) & 1 else -1.0
    return bucket, sign


@lru_cache(maxsize=4096)
def embed(text: str) -> tuple[float, ...]:
    """Unit-norm embedding for ``text``. Deterministic across processes."""
    vector = [0.0] * DIM
    for feature, weight in _features(text).items():
        bucket, sign = _hash_index(feature)
        vector[bucket] += sign * weight
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0.0:
        # Empty or stopword-only input: a stable zero vector never matches
        # anything above threshold, which is the correct behaviour.
        return tuple(vector)
    return tuple(v / norm for v in vector)


def embed_list(texts: list[str]) -> list[list[float]]:
    return [list(embed(t)) for t in texts]


def cosine_similarity(
    a: tuple[float, ...] | list[float], b: tuple[float, ...] | list[float]
) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    # Both operands are already unit-norm, so the dot product is the cosine.
    return max(-1.0, min(1.0, dot))


def similarity(text_a: str, text_b: str) -> float:
    return cosine_similarity(embed(text_a), embed(text_b))


__all__ = [
    "DIM",
    "content_tokens",
    "cosine_similarity",
    "embed",
    "embed_list",
    "normalize_text",
    "similarity",
    "tokenize",
]
