"""
Reranking bằng Cross-Encoder (bge-reranker-v2-m3).

Chấm lại độ liên quan y khoa giữa câu hỏi và từng tài liệu ứng viên, đưa tài liệu
quan trọng nhất lên đầu trước khi nạp vào prompt. Model được nạp lười (lazy) ở lần
dùng đầu tiên để không làm chậm khởi động server; nếu không tải được (thiếu lib/
mạng) thì tự bỏ qua rerank, hệ thống vẫn chạy bằng điểm fusion.
"""

from __future__ import annotations

import threading
from typing import List, Optional, Tuple

from core import config

_model = None
_load_failed = False
_lock = threading.Lock()


def _get_model():
    global _model, _load_failed
    if _model is not None or _load_failed:
        return _model
    with _lock:
        if _model is not None or _load_failed:
            return _model
        try:
            from sentence_transformers import CrossEncoder

            print(f"[Reranker] Đang nạp model: {config.RERANKER_MODEL_NAME} (lần đầu có thể tải ~2GB)...")
            _model = CrossEncoder(config.RERANKER_MODEL_NAME, max_length=512)
            print("[Reranker] ✅ Sẵn sàng.")
        except Exception as exc:  # pragma: no cover - phụ thuộc môi trường
            print(f"[Reranker] ⚠️ Không nạp được reranker ({exc}). Bỏ qua bước rerank.")
            _load_failed = True
            _model = None
    return _model


def is_available() -> bool:
    if not config.ENABLE_RERANKER:
        return False
    return _get_model() is not None


def rerank(
    query: str,
    docs: List[dict],
    top_k: Optional[int] = None,
    text_key: str = "text",
) -> Tuple[List[dict], bool]:
    """
    Sắp xếp lại ``docs`` theo điểm cross-encoder.

    Trả về (docs_đã_xếp, đã_rerank?). Mỗi doc được gắn thêm khoá ``rerank_score``.
    Nếu reranker không khả dụng thì trả nguyên thứ tự đầu vào.
    """
    if not docs:
        return docs, False

    if not config.ENABLE_RERANKER:
        return (docs[:top_k] if top_k else docs), False

    model = _get_model()
    if model is None:
        return (docs[:top_k] if top_k else docs), False

    pairs = [(query, d.get(text_key, "")) for d in docs]
    try:
        scores = model.predict(pairs)
    except Exception as exc:  # pragma: no cover
        print(f"[Reranker] ⚠️ Lỗi khi rerank ({exc}). Giữ nguyên thứ tự.")
        return (docs[:top_k] if top_k else docs), False

    for d, s in zip(docs, scores):
        d["rerank_score"] = float(s)

    ranked = sorted(docs, key=lambda d: d.get("rerank_score", 0.0), reverse=True)
    return (ranked[:top_k] if top_k else ranked), True
