from typing import Iterable


class RerankerUnavailable(RuntimeError):
    pass


_CROSS_ENCODER = None
_CROSS_ENCODER_MODEL = None


def _load_cross_encoder(model_name: str):
    global _CROSS_ENCODER
    global _CROSS_ENCODER_MODEL
    if _CROSS_ENCODER is not None and _CROSS_ENCODER_MODEL == model_name:
        return _CROSS_ENCODER
    try:
        from sentence_transformers import CrossEncoder
    except Exception as exc:  # pragma: no cover - optional dependency path
        raise RerankerUnavailable("sentence-transformers is not installed") from exc
    _CROSS_ENCODER = CrossEncoder(model_name)
    _CROSS_ENCODER_MODEL = model_name
    return _CROSS_ENCODER


def rerank_candidates(query: str, candidates: Iterable[dict], model_name: str) -> dict[str, float]:
    rows = list(candidates)
    if not rows:
        return {}
    model = _load_cross_encoder(model_name)
    pairs = []
    for row in rows:
        text = (
            f"path: {row.get('file_path') or ''}\n"
            f"language: {row.get('language') or ''}\n"
            f"content: {row.get('content') or ''}"
        )
        pairs.append((query, text))
    scores = model.predict(pairs)
    return {row["chunk_id"]: float(score) for row, score in zip(rows, scores, strict=False)}
