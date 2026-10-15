"""
Ingestion pipeline: OCR tài liệu -> chunking -> Vector DB.

Nâng cấp: chunking nhận biết cấu trúc bệnh án SOAP (Subjective/Objective/
Assessment/Plan). Với tài liệu có cấu trúc SOAP, mỗi chunk được gắn metadata
``soap_section`` để bảo toàn bệnh cảnh; với tài liệu y văn/phác đồ thông thường,
tự rơi về SentenceSplitter như trước. Giữ embedding tiếng Việt để tương thích.
"""

import os
import re
from dotenv import load_dotenv
from llama_index.core import (
    SimpleDirectoryReader,
    VectorStoreIndex,
    StorageContext,
    load_index_from_storage,
    Settings,
)
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import TextNode
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

from core.ocr_reader import OcrPdfReader

load_dotenv()

DATA_DIR = "./data"
PERSIST_DIR = "./vector_db"
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "keepitreal/vietnamese-sbert")

# Tiêu đề các mục SOAP (tiếng Việt + Anh). Dùng để phát hiện cấu trúc bệnh án.
SOAP_PATTERNS = [
    ("S", r"^\s*(?:S\s*[:\-.]|subjective|chủ quan|bệnh sử|lý do (?:vào|nhập) viện|than phiền)"),
    ("O", r"^\s*(?:O\s*[:\-.]|objective|khách quan|khám (?:lâm sàng|bệnh)|cận lâm sàng|sinh hiệu)"),
    ("A", r"^\s*(?:A\s*[:\-.]|assessment|đánh giá|chẩn đoán)"),
    ("P", r"^\s*(?:P\s*[:\-.]|plan|kế hoạch|hướng (?:điều trị|xử trí)|điều trị)"),
]
_SOAP_COMPILED = [(tag, re.compile(pat, re.IGNORECASE)) for tag, pat in SOAP_PATTERNS]


def initialize_rag_pipeline():
    Settings.embed_model = HuggingFaceEmbedding(
        model_name=EMBEDDING_MODEL_NAME,
        trust_remote_code=True,
    )
    Settings.text_splitter = SentenceSplitter(chunk_size=1024, chunk_overlap=100)


def _detect_soap_section(line: str):
    for tag, pat in _SOAP_COMPILED:
        if pat.match(line):
            return tag
    return None


def _has_soap_structure(text: str) -> bool:
    found = set()
    for line in text.splitlines():
        tag = _detect_soap_section(line)
        if tag:
            found.add(tag)
    # Coi là bệnh án SOAP nếu xuất hiện >= 3/4 mục.
    return len(found) >= 3


def _soap_aware_nodes(document, splitter: SentenceSplitter):
    """Chia 1 document theo mục SOAP, mỗi mục lại chia nhỏ bằng splitter."""
    text = document.get_content()
    base_meta = dict(document.metadata or {})

    if not _has_soap_structure(text):
        nodes = splitter.get_nodes_from_documents([document])
        return nodes

    # Gom dòng vào từng mục SOAP.
    sections = []
    current_tag = "GEN"
    buffer = []
    for line in text.splitlines():
        tag = _detect_soap_section(line)
        if tag:
            if buffer:
                sections.append((current_tag, "\n".join(buffer)))
                buffer = []
            current_tag = tag
        buffer.append(line)
    if buffer:
        sections.append((current_tag, "\n".join(buffer)))

    soap_label = {"S": "Chủ quan", "O": "Khách quan", "A": "Đánh giá", "P": "Kế hoạch", "GEN": "Chung"}
    nodes = []
    for tag, seg_text in sections:
        if len(seg_text.strip()) < 10:
            continue
        for chunk in splitter.split_text(seg_text):
            meta = dict(base_meta)
            meta["soap_section"] = soap_label.get(tag, tag)
            nodes.append(TextNode(text=chunk, metadata=meta))
    return nodes


def load_or_create_index():
    initialize_rag_pipeline()

    if not os.path.exists(os.path.join(PERSIST_DIR, "docstore.json")):
        print("🚀 Khởi động Luồng Ingestion (OCR + SOAP-aware chunking)...")

        reader = SimpleDirectoryReader(
            DATA_DIR,
            required_exts=[".pdf", ".txt"],
            file_extractor={".pdf": OcrPdfReader(tesseract_lang="vie")},
        )
        documents = reader.load_data()
        print(f"📄 Đã đọc xong {len(documents)} tài liệu.")

        splitter = Settings.text_splitter
        raw_nodes = []
        soap_docs = 0
        for doc in documents:
            if _has_soap_structure(doc.get_content()):
                soap_docs += 1
            raw_nodes.extend(_soap_aware_nodes(doc, splitter))

        valid_nodes = [n for n in raw_nodes if len(n.get_content().strip()) > 20]
        print(f"🧩 Băm & lọc nhiễu: {len(valid_nodes)} chunk chất lượng ({soap_docs} tài liệu dạng SOAP).")

        print("⚡ Tạo Vector DB (Local Embedding)...")
        index = VectorStoreIndex(valid_nodes, show_progress=True)
        index.storage_context.persist(persist_dir=PERSIST_DIR)
        print("✅ Đã lưu Vector DB thành công!")
    else:
        print("⚡ Đã tìm thấy Vector DB local. Đang load...")
        storage_context = StorageContext.from_defaults(persist_dir=PERSIST_DIR)
        index = load_index_from_storage(storage_context)
        print("✅ Load Vector DB thành công!")

    return index


if __name__ == "__main__":
    print("Bắt đầu chạy thử Ingestion Pipeline...")
    index = load_or_create_index()
    print("Sẵn sàng cho việc truy xuất (Retrieval)!")
