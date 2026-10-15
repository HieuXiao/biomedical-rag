"""
Tầng nạp Vector Index & Embedding model dùng chung cho toàn hệ thống.

Tách riêng để Hybrid Retriever, Generator và các script cùng tái sử dụng một
instance index (tránh load nhiều lần tốn RAM). Giữ nguyên embedding tiếng Việt
để tương thích Vector DB đã build sẵn.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import List

from llama_index.core import StorageContext, load_index_from_storage
from llama_index.core.settings import Settings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

from core import config

_embed_model = None
_index = None
_nodes_cache: List = []
_generation = 0  # tăng mỗi khi tập node thay đổi (để BM25 build lại)
# RLock (reentrant) vì get_index() giữ lock rồi gọi get_embed_model()/get_all_nodes()
# vốn cũng cần lock — dùng Lock thường sẽ tự khoá chính mình (deadlock).
_lock = threading.RLock()


def resolve_vector_store_dir() -> Path:
    for path in config.VECTOR_STORE_CANDIDATES:
        p = Path(path)
        if p.exists():
            return p
    raise FileNotFoundError(
        "Không tìm thấy thư mục Vector DB. Đã kiểm tra: "
        + ", ".join(config.VECTOR_STORE_CANDIDATES)
    )


def get_embed_model() -> HuggingFaceEmbedding:
    global _embed_model
    if _embed_model is None:
        with _lock:
            if _embed_model is None:
                print(f"[Index] Nạp embedding: {config.EMBEDDING_MODEL_NAME}...")
                _embed_model = HuggingFaceEmbedding(
                    model_name=config.EMBEDDING_MODEL_NAME,
                    trust_remote_code=True,
                )
    return _embed_model


def get_index():
    """Nạp (một lần) VectorStoreIndex từ đĩa."""
    global _index
    if _index is None:
        with _lock:
            if _index is None:
                Settings.embed_model = get_embed_model()
                # Tắt LLM mặc định (OpenAI) của LlamaIndex để tránh treo/đòi
                # OPENAI_API_KEY khi load index. Pipeline dùng Gemini trực tiếp
                # qua self.llm nên không cần Settings.llm.
                Settings.llm = None
                vector_dir = resolve_vector_store_dir()
                print(f"[Index] Nạp Vector Index từ: {vector_dir}")
                storage_context = StorageContext.from_defaults(persist_dir=str(vector_dir))
                _index = load_index_from_storage(storage_context)
    return _index


def get_all_nodes() -> List:
    """Trả về toàn bộ node (chunk) trong docstore để dựng corpus BM25."""
    global _nodes_cache
    if not _nodes_cache:
        index = get_index()
        docstore = index.storage_context.docstore
        _nodes_cache = list(docstore.docs.values())
    return _nodes_cache


def get_generation() -> int:
    return _generation


def invalidate_nodes_cache():
    """Xoá cache node (gọi sau khi thêm/xoá tài liệu để BM25 build lại)."""
    global _nodes_cache, _generation
    _nodes_cache = []
    _generation += 1


def add_nodes(nodes: List, persist: bool = True):
    """Chèn thêm node vào index (dùng khi user upload tài liệu) và lưu đĩa."""
    if not nodes:
        return
    with _lock:
        index = get_index()
        index.insert_nodes(nodes)
        if persist:
            vector_dir = resolve_vector_store_dir()
            index.storage_context.persist(persist_dir=str(vector_dir))
        invalidate_nodes_cache()


def delete_nodes_by_doc_key(doc_key: str, persist: bool = True):
    """Xoá mọi node thuộc 1 tài liệu (theo metadata doc_key)."""
    with _lock:
        index = get_index()
        docstore = index.storage_context.docstore
        target_ids = [nid for nid, n in docstore.docs.items()
                      if n.metadata.get("doc_key") == doc_key]
        for nid in target_ids:
            try:
                index.delete_nodes([nid])
            except Exception:
                try:
                    docstore.delete_document(nid)
                except Exception:
                    pass
        if persist and target_ids:
            vector_dir = resolve_vector_store_dir()
            index.storage_context.persist(persist_dir=str(vector_dir))
        invalidate_nodes_cache()
        return len(target_ids)
