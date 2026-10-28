import hashlib
import os
import re
from functools import lru_cache

import numpy as np
from rapidfuzz.fuzz import ratio

from app.core.config import settings

MODEL_STATUS = {"backend": "not_loaded", "model": settings.embedding_model, "error": None}

# Local inference is PyTorch-based. Avoid importing an unrelated host Keras stack.
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")


def normalize_name(value: str) -> str:
    value = re.sub(r"[^a-z0-9 ]", " ", value.lower())
    stop = {"the", "of", "and", "society", "trust"}
    return " ".join(x for x in value.split() if x not in stop)


@lru_cache(maxsize=1)
def _model():
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(settings.embedding_model)
        MODEL_STATUS.update(backend="sentence-transformers", error=None)
        return model
    except Exception as exc:  # deterministic degradation keeps workflows available
        MODEL_STATUS.update(backend="feature-hash-fallback", error=str(exc)[:300])
        return None


def _feature_hash(text: str, dims: int = 384) -> np.ndarray:
    vector = np.zeros(dims, dtype=np.float32)
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    grams = tokens + [f"{tokens[i]}_{tokens[i + 1]}" for i in range(max(0, len(tokens) - 1))]
    for gram in grams:
        digest = hashlib.blake2b(gram.encode(), digest_size=8).digest()
        idx = int.from_bytes(digest, "little") % dims
        vector[idx] += 1.0
    norm = np.linalg.norm(vector)
    return vector / norm if norm else vector


def embed(text: str) -> tuple[list[float], str]:
    model = _model()
    if model:
        vector = model.encode([text], normalize_embeddings=True, show_progress_bar=False)[0]
        return vector.astype(float).tolist(), "sentence-transformers"
    return _feature_hash(text).astype(float).tolist(), "feature-hash-fallback"


def cosine(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a), np.array(b)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    return float(np.dot(va, vb) / denom) if denom else 0.0


def score_pair(a, b, vector_a=None, vector_b=None) -> dict:
    same_institution = a.institution_id == b.institution_id
    cross_bureau = a.assigned_bureau_id != b.assigned_bureau_id
    active = a.status.value != "disposed" and b.status.value != "disposed"
    category_match = a.category_id == b.category_id
    if vector_a is None:
        vector_a, backend = embed(f"{a.title}. {a.description}")
    else:
        backend = MODEL_STATUS["backend"]
    if vector_b is None:
        vector_b, _ = embed(f"{b.title}. {b.description}")
    semantic = cosine(vector_a, vector_b)
    components = {
        "semantic": round(semantic * 0.62, 4),
        "institution": 0.18 if same_institution else 0.0,
        "category": 0.08 if category_match else 0.0,
        "cross_bureau": 0.07 if cross_bureau else 0.0,
        "active_cases": 0.05 if active else 0.0,
    }
    hybrid = min(1.0, sum(components.values()))
    reasons = []
    if same_institution:
        reasons.append("Same verified canonical institution and AICTE Permanent ID")
    if cross_bureau:
        reasons.append("Cases are owned by different participating bureaus")
    if active:
        reasons.append("Both complaints are currently active")
    if category_match:
        reasons.append("Complaint categories match")
    if semantic >= 0.72:
        reasons.append(f"Strong semantic similarity ({semantic:.0%})")
    elif semantic >= 0.48:
        reasons.append(f"Moderate semantic similarity ({semantic:.0%})")
    else:
        reasons.append(f"Low semantic similarity ({semantic:.0%}); shared institution alone does not imply duplication")
    if same_institution and semantic >= 0.82 and category_match:
        finding_type = "likely_duplicate"
    elif same_institution and cross_bureau and semantic >= 0.52:
        finding_type = "cross_bureau_related"
    elif same_institution and cross_bureau:
        finding_type = "shared_institution_activity"
    elif semantic >= 0.86:
        finding_type = "similar_different_institution"
    else:
        finding_type = "unrelated"
    severity = "critical" if hybrid >= 0.9 else "high" if hybrid >= 0.75 else "medium" if hybrid >= 0.55 else "low"
    return {
        "semantic": round(semantic, 4),
        "hybrid": round(hybrid, 4),
        "finding_type": finding_type,
        "severity": severity,
        "reasons": reasons,
        "backend": backend,
        "model": settings.embedding_model,
        "embedding_dimensions": len(vector_a),
        "facts": {
            "same_institution": same_institution,
            "category_match": category_match,
            "cross_bureau": cross_bureau,
            "both_active": active,
        },
        "components": components,
        "weights": {
            "semantic": 0.62,
            "institution": 0.18,
            "category": 0.08,
            "cross_bureau": 0.07,
            "active_cases": 0.05,
        },
        "thresholds": {
            "stored_finding": 0.42,
            "cross_bureau_related_semantic": 0.52,
            "likely_duplicate_semantic": 0.82,
            "similar_different_institution_semantic": 0.86,
        },
    }


def institution_similarity(a: str, b: str) -> float:
    return ratio(normalize_name(a), normalize_name(b)) / 100

