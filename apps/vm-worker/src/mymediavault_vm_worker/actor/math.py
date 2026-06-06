from __future__ import annotations

from collections.abc import Iterable

import numpy as np

def normalize_embedding(value: np.ndarray) -> np.ndarray:
    embedding = np.asarray(value, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(embedding))
    if norm == 0:
        raise ValueError("Face embedding must not be zero.")
    return embedding / norm


def normalized_mean(values: Iterable[np.ndarray]) -> np.ndarray:
    embeddings = [normalize_embedding(value) for value in values]
    if not embeddings:
        raise ValueError("At least one face embedding is required.")
    return normalize_embedding(np.mean(embeddings, axis=0))


def cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.dot(normalize_embedding(left), normalize_embedding(right)))


