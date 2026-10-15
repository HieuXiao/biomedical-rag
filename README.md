# Biomedical RAG — Clinical Medical RAG

Trợ lý y tế cấp lâm sàng dựa trên kiến trúc **Medical RAG nâng cao**: khử định danh
PHI, định tuyến truy vấn, **GraphRAG** (Knowledge Graph) + **Hybrid Search**
(Vector + BM25 + RRF + Cross-encoder Reranker), sinh câu trả lời có **trích dẫn
nguồn** và **kiểm tra bám nguồn (Med-FactCheck)**, trả về qua **SSE streaming**.

## Kiến trúc & Luồng xử lý

```
Giao diện Bác sĩ (React, SSE)
        │
        ▼
1. Khử định danh PHI          core/deidentify.py     (regex tiếng Việt: Tên, ID, Ngày, SĐT, Địa chỉ)
2. Intent Router              core/intent_router.py  (phân luồng Phác đồ / Bệnh án)
        ├────────────── Luồng Phác đồ (GraphRAG) ──────────────┐
        │  3. Knowledge Graph   core/graph_store.py             │
        │     Entity Matching → Graph Traversal → Triple Text   │
        │     (Neo4j Community, fallback in-memory)              │
        │                                                        │
        └────────────── Luồng chung (Hybrid Search) ───────────┘
           4. Hybrid Retrieval  core/hybrid_retriever.py
              Vector (vietnamese-sbert) + BM25 → RRF → Rerank (bge-reranker-v2-m3)
        │
        ▼
5. LLM Generation             core/generator.py      (Gemini + citation-enforced prompt, retry 503)
6. Med-FactCheck              core/factcheck.py      (grounding, phát hiện ảo giác)
7. Re-identification          core/deidentify.py     (khôi phục token PHI ở local)
        │
        ▼
Phản hồi: answer + citations + pipeline trace  (SSE streaming / JSON)
```

So với kiến trúc gốc, phiên bản này **lược bỏ các phần tốn chi phí không cần
thiết** (đã trao đổi): dùng **đồ thị y khoa tự curate** (ICD-10 miễn phí, tránh
bản quyền SNOMED/UMLS), **de-id bằng regex tiếng Việt** thay cho Presidio, giữ
Vector DB `vietnamese-sbert` sẵn có thay vì re-embed BGE-M3 + Qdrant. Tất cả hạ
tầng đều **self-host $0** (khoản tốn tiền duy nhất là API Gemini).

## Thành phần chính

| Khối | File | Công nghệ |
|---|---|---|
| Khử định danh PHI | [backend/core/deidentify.py](backend/core/deidentify.py) | Regex/pattern tiếng Việt |
| Intent Router | [backend/core/intent_router.py](backend/core/intent_router.py) | Heuristic từ khoá |
| Knowledge Graph | [backend/core/graph_store.py](backend/core/graph_store.py) · [seed](backend/core/graph_seed.py) | Neo4j Community / in-memory |
| Hybrid Retrieval | [backend/core/hybrid_retriever.py](backend/core/hybrid_retriever.py) | BM25 + Vector + RRF |
| Reranker | [backend/core/reranker.py](backend/core/reranker.py) | Cross-encoder `bge-reranker-v2-m3` |
| Pipeline / LLM | [backend/core/generator.py](backend/core/generator.py) | Gemini (google-genai) |
| Med-FactCheck | [backend/core/factcheck.py](backend/core/factcheck.py) | Grounding overlap |
| Ingestion (SOAP-aware) | [backend/core/ingestion.py](backend/core/ingestion.py) | OCR + SOAP chunking |
| API | [backend/api/routes.py](backend/api/routes.py) | FastAPI + SSE |
| Frontend | [frontend/src/App.jsx](frontend/src/App.jsx) | React 19, Vite 8 |

## Yêu cầu

- Python 3.10+ (khuyến nghị 3.11+), Node.js 18+ và npm
- Tesseract OCR (ngôn ngữ `vie`) + Poppler — chỉ cần khi chạy lại ingestion cho PDF ảnh
- Docker Desktop — chỉ cần nếu muốn chạy Neo4j thật (không bắt buộc, có fallback)
- RAM ≥ 8GB khuyến nghị (reranker `bge-reranker-v2-m3` ~2.3GB)

## Cấu hình (.env)

Tạo `backend/.env` từ mẫu [backend/.env.example](backend/.env.example). Tối thiểu:

```env
GEMINI_API_KEY=your_key_here
```

Các feature flag (mặc định bật hết, có thể tắt để nhẹ):

```env
ENABLE_DEID=true
ENABLE_GRAPH=true
ENABLE_RERANKER=true        # tắt (false) nếu máy yếu / không muốn tải 2.3GB
ENABLE_FACTCHECK=true
GRAPH_INMEMORY_FALLBACK=true
DEFAULT_MODEL=gemini-3.5-flash
```

> **Lưu ý model**: họ `gemini-2.5-*` đã bị Google chặn với tài khoản mới (404).
> Dự án dùng họ **`gemini-3.x`** (mặc định `gemini-3.5-flash`). Khi một model quá
> tải (503) hoặc hết quota, backend tự retry và frontend tự fallback sang model kế.

## Chạy project

### 1) Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

API mặc định: `http://127.0.0.1:8001`. Lần chạy đầu sẽ tải embedding
`vietnamese-sbert` (~500MB) và (nếu bật) reranker (~2.3GB).

### 2) Neo4j Knowledge Graph (tuỳ chọn — không có vẫn chạy bằng in-memory)

```powershell
docker compose up -d neo4j      # từ thư mục gốc dự án
cd backend
python scripts/build_graph.py   # nạp đồ thị y khoa seed vào Neo4j
```

Neo4j Browser: `http://localhost:7474` (user `neo4j` / pass `medicalrag`).

### 3) Frontend

```powershell
cd frontend
npm install
npm run dev
```

UI theo URL Vite in ra (thường `http://127.0.0.1:5173`).

## Web app (Auth, Lịch sử, Save box, Admin, Profile)

- **Đăng nhập/Đăng ký** (JWT + bcrypt). Admin mặc định: `admin@medrag.local` / `admin123` (đổi ngay trong `.env`).
- **Lịch sử chat theo account** (SQLite) + **left sidebar** liệt kê hội thoại.
- **Save box**: user upload tài liệu riêng (PDF/TXT/MD) → embed vào RAG, bật/tắt từng tài liệu; truy xuất chỉ dùng tài liệu hệ thống + tài liệu riêng đang bật (cô lập theo user).
- **Admin**: quản lý tài liệu gốc hệ thống (thêm/bật/tắt/xoá), danh sách người dùng, dashboard hoạt động (số liệu, log, bám nguồn TB).
- **Profile**: hồ sơ (chuyên khoa, yêu cầu riêng) được chèn vào prompt để cá nhân hoá.
- DB: `backend/data/app.db` (tự tạo). Endpoint auth cần header `Authorization: Bearer <token>`.

## API

| Method | Endpoint | Mô tả |
|---|---|---|
| GET | `/api/health` | Trạng thái + feature flags đang bật |
| GET | `/api/models` | Danh sách model + usage theo ngày |
| GET | `/api/pipeline/info` | Mô tả 7 tầng pipeline (cho UI) |
| POST | `/api/chat` | Hỏi đáp RAG (non-stream, JSON đầy đủ: answer, citations, pipeline) |
| POST | `/api/chat/stream` | Hỏi đáp RAG qua **SSE** (event: `pipeline` → `token*` → `done`) |

Body `POST /api/chat[/stream]`:

```json
{ "message": "Metformin chống chỉ định khi nào?", "model": "gemini-3.5-flash", "api_key": "" }
```

## Thư mục dữ liệu

- `backend/data/` — PDF/TXT đầu vào
- `backend/vector_db/` — Vector DB (đã build sẵn; xoá đi để ingestion build lại)

## Bảo mật

- `backend/.env` đã nằm trong `.gitignore` — **không commit API key**.
- PHI được ẩn danh trước khi gửi LLM và chỉ khôi phục ở môi trường local.
