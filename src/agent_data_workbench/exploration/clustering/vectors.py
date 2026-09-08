"""Sparse TF-IDF weights and cosine similarity, independent of stored traces."""

import math
from collections import Counter


def tfidf_vectors(documents: list[Counter[str]]) -> list[dict[str, float]]:
    """Use log term frequency, smoothed inverse frequency and unit-length vectors."""
    frequency = Counter(term for counts in documents for term in counts)
    vectors = []
    for counts in documents:
        vector = {
            term: (1 + math.log(count))
            * (1 + math.log((len(documents) + 1) / (frequency[term] + 1)))
            for term, count in counts.items()
        }
        norm = math.sqrt(sum(weight * weight for weight in vector.values()))
        vectors.append({term: weight / norm for term, weight in vector.items()})
    return vectors


def cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    """Compute the dot product of two already normalized sparse vectors."""
    return sum(weight * right.get(term, 0) for term, weight in left.items())
