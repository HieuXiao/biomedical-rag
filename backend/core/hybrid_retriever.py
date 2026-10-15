"""
Hybrid Retriever: kết hợp tìm kiếm Vector (ngữ nghĩa) + BM25 (từ khoá) và hợp
nhất bằng Reciprocal Rank Fusion (RRF), sau đó Rerank bằng cross-encoder.

Lý do dùng hybrid trong y khoa:
  - BM25 bắt đúng thuật ngữ/chính tả y tế (tên thuốc, mã ICD, liều).
  - Vector bắt ngữ nghĩa (diễn đạt khác nhau cùng ý).
  - RRF trộn 2 bảng xếp hạng mà không cần chuẩn hoá điểm.
  - Cross-encoder rerank chọn ra top tài liệu liên quan nhất cho chẩn đoán.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from typing import Dict, List

from core import config, reranker
from core import index_store


def _tokenize(text: str) -> List[str]:
    # Tokenise thô cho tiếng Việt: hạ chữ thường + tách theo khoảng trắng/ký tự.
    return re.findall(r"[0-9a-zàáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ]+",
                      (text or "").lower())


@dataclass
class RetrievalResult:
    nodes: List[dict] = field(default_factory=list)   # [{text, score, file_name, ...}]
    method: str = "hybrid"
    reranked: bool = False
    stats: Dict = field(default_factory=dict)


class HybridRetriever:
    def __init__(self):
        self._bm25 = None
        self._bm25_nodes: List = []
        self._bm25_gen = -1
        self._lock = threading.Lock()

    # ---- BM25 ----------------------------------------------------------
    def _ensure_bm25(self):
        gen = index_store.get_generation()
        if self._bm25 is not None and self._bm25_gen == gen:
            return
        with self._lock:
            gen = index_store.get_generation()
            if self._bm25 is not None and self._bm25_gen == gen:
                return
            try:
                from rank_bm25 import BM25Okapi
            except Exception as exc:  # pragma: no cover
                print(f"[Hybrid] ⚠️ Thiếu rank-bm25 ({exc}). Chỉ dùng Vector search.")
                self._bm25 = False  # đánh dấu không khả dụng
                self._bm25_gen = gen
                return

            nodes = index_store.get_all_nodes()
            corpus = [_tokenize(n.get_content()) for n in nodes]
            self._bm25_nodes = nodes
            self._bm25 = BM25Okapi(corpus) if corpus else False
            self._bm25_gen = gen
            print(f"[Hybrid] BM25 index (re)build với {len(corpus)} chunk.")

    def _bm25_search(self, query: str, top_k: int) -> List:
        self._ensure_bm25()
        if not self._bm25:
            return []
        scores = self._bm25.get_scores(_tokenize(query))
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return [(self._bm25_nodes[i], float(scores[i])) for i in ranked[:top_k] if scores[i] > 0]

    # ---- Vector --------------------------------------------------------
    def _vector_search(self, query: str, top_k: int) -> List:
        index = index_store.get_index()
        retriever = index.as_retriever(similarity_top_k=top_k)
        results = retriever.retrieve(query)
        return [(r.node, float(r.score or 0.0)) for r in results]

    # ---- RRF fusion ----------------------------------------------------
    @staticmethod
    def _rrf(rankings: List[List], k: int) -> Dict[str, float]:
        fused: Dict[str, float] = {}
        for ranking in rankings:
            for rank, (node, _score) in enumerate(ranking):
                nid = node.node_id
                fused[nid] = fused.get(nid, 0.0) + 1.0 / (k + rank + 1)
        return fused

    @staticmethod
    def _is_allowed(node, allowed_keys, base_allowed) -> bool:
        """Node được phép nếu thuộc tài liệu user được xem, hoặc là node gốc hệ thống."""
        if allowed_keys is None:
            return True  # không scope (vd: chưa tích hợp auth)
        dk = node.metadata.get("doc_key")
        if dk is None:
            return base_allowed       # node Vector DB gốc (phác đồ có sẵn)
        return dk in allowed_keys

    # ---- Public --------------------------------------------------------
    def retrieve(self, query: str, final_top_k: int = None,
                 allowed_keys=None, base_allowed: bool = True) -> RetrievalResult:
        final_top_k = final_top_k or config.FINAL_TOP_K

        # Khi có lọc theo scope, lấy pool ứng viên rộng hơn để không bị thiếu.
        pool = max(config.VECTOR_TOP_K, 24) if allowed_keys is not None else config.VECTOR_TOP_K
        vec = self._vector_search(query, pool)
        bm25 = self._bm25_search(query, pool)

        # Lọc theo quyền truy cập tài liệu.
        vec = [(n, s) for (n, s) in vec if self._is_allowed(n, allowed_keys, base_allowed)]
        bm25 = [(n, s) for (n, s) in bm25 if self._is_allowed(n, allowed_keys, base_allowed)]

        node_by_id = {}
        for node, _ in vec + bm25:
            node_by_id[node.node_id] = node

        fused_scores = self._rrf([vec, bm25], config.RRF_K)
        fused_ids = sorted(fused_scores, key=lambda i: fused_scores[i], reverse=True)
        fused_ids = fused_ids[: config.FUSED_TOP_K]

        candidates: List[dict] = []
        for nid in fused_ids:
            node = node_by_id[nid]
            candidates.append({
                "node_id": nid,
                "text": node.get_content(),
                "file_name": node.metadata.get("file_name", "Tài liệu y khoa"),
                "section": node.metadata.get("soap_section"),
                "page": node.metadata.get("page_label") or node.metadata.get("page"),
                "fusion_score": round(fused_scores[nid], 5),
            })

        reranked_docs, did_rerank = reranker.rerank(query, candidates, top_k=final_top_k)

        return RetrievalResult(
            nodes=reranked_docs,
            method="hybrid-rrf" + ("+rerank" if did_rerank else ""),
            reranked=did_rerank,
            stats={
                "vector_hits": len(vec),
                "bm25_hits": len(bm25),
                "fused": len(fused_ids),
                "returned": len(reranked_docs),
            },
        )


# Singleton
_retriever = None
_retriever_lock = threading.Lock()


def get_retriever() -> HybridRetriever:
    global _retriever
    if _retriever is None:
        with _retriever_lock:
            if _retriever is None:
                _retriever = HybridRetriever()
    return _retriever
