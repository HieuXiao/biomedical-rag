"""Dịch vụ nghiệp vụ: ingest tài liệu upload, cá nhân hoá, phân quyền truy xuất."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Set, Tuple

from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import Document as LIDocument

from core import index_store
from core.db import BASE_INDEX_MARKER
from core.models import Document, User
from core.ocr_reader import OcrPdfReader
from core.ingestion import _soap_aware_nodes

_splitter = SentenceSplitter(chunk_size=1024, chunk_overlap=100)


def build_profile_text(user: User) -> str:
    """Tạo đoạn mô tả hồ sơ người dùng để chèn vào prompt (cá nhân hoá)."""
    bits = []
    if user.full_name:
        bits.append(f"Người dùng: {user.full_name}")
    if user.title:
        bits.append(f"Chức danh: {user.title}")
    if user.specialty:
        bits.append(f"Chuyên khoa: {user.specialty}")
    if user.workplace:
        bits.append(f"Nơi công tác: {user.workplace}")
    if user.personalization:
        bits.append(f"Yêu cầu riêng về cách trả lời: {user.personalization}")
    if not bits:
        return ""
    return ("Hãy điều chỉnh câu trả lời cho phù hợp với người dùng sau "
            "(không bịa thêm thông tin ngoài tài liệu):\n" + "\n".join(f"- {b}" for b in bits))


def allowed_doc_scope(db, user: User) -> Tuple[Optional[Set[str]], bool]:
    """
    Trả về (allowed_keys, base_allowed):
      - allowed_keys: tập doc_key (f"doc:{id}") của tài liệu user được phép truy xuất
        (tài liệu hệ thống đang bật + tài liệu riêng của user đang bật).
      - base_allowed: khối Vector DB gốc (phác đồ có sẵn) có đang bật không.
    """
    docs = db.query(Document).filter(
        Document.active == True,  # noqa: E712
        ((Document.scope == "system") | (Document.owner_id == user.id)),
    ).all()

    allowed: Set[str] = set()
    base_allowed = False
    for d in docs:
        if d.stored_path == BASE_INDEX_MARKER:
            base_allowed = True
        else:
            allowed.add(f"doc:{d.id}")
    return allowed, base_allowed


def _read_file_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        reader = OcrPdfReader(tesseract_lang="vie")
        docs = reader.load_data(str(path))
        return "\n\n".join(d.get_content() for d in docs)
    # txt / md
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def ingest_document(doc: Document) -> int:
    """
    Đọc file của 1 Document, chunk (SOAP-aware), gắn metadata doc_key và chèn vào
    index. Trả về số chunk đã thêm.
    """
    path = Path(doc.stored_path)
    if not path.exists():
        return 0

    text = _read_file_text(path)
    if not text or len(text.strip()) < 20:
        return 0

    base_meta = {
        "file_name": doc.filename,
        "doc_key": f"doc:{doc.id}",
        "scope": doc.scope,
        "owner_id": doc.owner_id,
    }
    li_doc = LIDocument(text=text, metadata=base_meta)
    nodes = _soap_aware_nodes(li_doc, _splitter)
    nodes = [n for n in nodes if len(n.get_content().strip()) > 20]
    # Đảm bảo mọi node đều mang metadata doc_key (kể cả nhánh SOAP).
    for n in nodes:
        n.metadata.update(base_meta)

    index_store.add_nodes(nodes)
    return len(nodes)


def remove_document_from_index(doc: Document) -> int:
    if doc.stored_path == BASE_INDEX_MARKER:
        return 0  # không cho xoá khối gốc khỏi index
    return index_store.delete_nodes_by_doc_key(f"doc:{doc.id}")
